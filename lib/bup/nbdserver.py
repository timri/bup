import SocketServer
from bup.helpers import *

SocketServer.TCPServer.allow_reuse_address = True 

class NbdServer(SocketServer.TCPServer):
    """
    Class implementing a NbdServer.
    """

    def __init__(self, roots, host = '127.0.0.1', port = 10809):
        """
        roots is a dict containing name => vfs.File mappings
        host and port are pretty self explaining
        
        this server currently allows only one connection at a time
        to support multiple concurrent connections, its possible to
        inherit from ThreadingTCPServer or ForkingTCPServer
        """
        SocketServer.TCPServer.__init__(self, (host, port), NbdTCPHandler)
        self.roots = roots

class NbdTCPHandler(SocketServer.StreamRequestHandler):
    """
    Handles a connection from a nbd-client (new-style)
    This class is instantiated once for each connection
    and lives for the whole connection
    (once handle returns the server closes the socket)
    """

    # NBD's magic (IHAVEOPT)
    NBD_HANDSHAKE = 0x49484156454F5054
    NBD_REPLY = 0x3e889045565a9

    NBD_REQUEST = 0x25609513
    NBD_RESPONSE = 0x67446698

    NBD_OPT_EXPORTNAME = 1
    NBD_OPT_ABORT = 2
    NBD_OPT_LIST = 3

    NBD_REP_ACK = 1
    NBD_REP_SERVER = 2
    NBD_REP_ERR_UNSUP = 2**31 + 1

    NBD_CMD_READ = 0
    NBD_CMD_WRITE = 1
    NBD_CMD_DISC = 2
    NBD_CMD_FLUSH = 3

    # fixed newstyle handshake
    NBD_HANDSHAKE_FLAGS = (1 << 0)

    # has flags, supports flush
    NBD_EXPORT_FLAGS = (1 << 0) ^ (1 << 2)
    NBD_RO_FLAG = (1 << 1)

    def nbd_response(self, fob, handle, error=0, data=None):
        fob.write(struct.pack('>LLQ', self.NBD_RESPONSE, error, handle))
        if data:
            fob.write(data)
        fob.flush()

    def handle(self):
        """ handle the connection """
        host, port = self.client_address
        root, node = None, None
        filereader = None
        log("Incoming connection from %s:%s\n" % (host, port))
        try:
            # initial handshake
            self.wfile.write("NBDMAGIC" + struct.pack(">QH", self.NBD_HANDSHAKE, self.NBD_HANDSHAKE_FLAGS))
            self.wfile.flush()

            data = self.rfile.read(4)
            try:
                client_flag = struct.unpack(">L", data)[0]
            except struct.error:
                raise IOError("Handshake failed, disconnecting")

            # we support both fixed and unfixed new-style handshake
            if client_flag == 0:
                fixed = False
                log("Client using new-style non-fixed handshake\n") #warn
            elif client_flag & 1 == 1:
                fixed = True
            else:
                raise IOError("Handshake failed, disconnecting")

            # negotiation phase
            while True:
                header = self.rfile.read(16)
                try:
                    (magic, opt, length) = struct.unpack(">QLL", header)
                except struct.error:
                    raise IOError("Negotiation failed: Invalid request, disconnecting")

                if magic != self.NBD_HANDSHAKE:
                    raise IOError("Negotiation failed: bad magic number: %s" % magic)

                if length:
                    data = self.rfile.read(length)
                    if(len(data) != length):
                        raise IOError("Negotiation failed: %s bytes expected" % length)
                else:
                    data = None

                debug1("[%s:%s]: opt=%s, len=%s, data=%s\n" % (host, port, opt, length, data))

                if opt == self.NBD_OPT_EXPORTNAME:
                    """ client requests a specific export """
                    if not data:
                        raise IOError("Negotiation failed: no export name was provided")

                    if data not in self.server.roots:
                        if not fixed:
                            raise IOError("Negotiation failed: unknown export name")

                        self.wfile.write(struct.pack(">QLLL", self.NBD_REPLY, opt, self.NBD_REP_ERR_UNSUP, 0))
                        self.wfile.flush()
                        continue

                    # we have negotiated a file and it will be used
                    # until the client disconnects
                    root = data
                    node = self.server.roots[data]
                    log("[%s:%s] Negotiated export: %s => %s\n" % (host, port, root, node.hash.encode('hex')))
                    filereader = node.open()
                    export_flags = self.NBD_EXPORT_FLAGS
#                    if store.read_only:
                    # bup-repositories are always read-only
                    export_flags ^= self.NBD_RO_FLAG
                    self.wfile.write(struct.pack('>QH', filereader.size, export_flags) + "\x00"*124)
                    self.wfile.flush()
                    # break out of negotiation
                    break

                elif opt == self.NBD_OPT_LIST:
                    """ client requests list of exports """
                    for container in self.server.roots.keys():
                        self.wfile.write(struct.pack(">QLLL", self.NBD_REPLY, opt, self.NBD_REP_SERVER, len(container) + 4))
                        self.wfile.write(struct.pack(">L", len(container)) + container)
                        self.wfile.flush()

                    self.wfile.write(struct.pack(">QLLL", self.NBD_REPLY, opt, self.NBD_REP_ACK, 0))
                    self.wfile.flush()

                elif opt == self.NBD_OPT_ABORT:
                    """ client wants to abort the connection """
                    self.wfile.write(struct.pack(">QLLL", self.NBD_REPLY, opt, self.NBD_REP_ACK, 0))
                    self.wfile.flush()

                    raise IOError("Client aborted negotiation")

                else:
                    # we don't support any other option
                    if not fixed:
                        raise IOError("Unsupported option")

                    self.wfile.write(struct.pack(">QLLL", self.NBD_REPLY, opt, self.NBD_REP_ERR_UNSUP, 0))
                    self.wfile.flush()

            # operation phase
            while True:
                header = self.rfile.read(28)
                try:
                    (magic, cmd, handle, offset, length) = struct.unpack(">LLQQL", header)
                except struct.error:
                    raise IOError("Invalid request, disconnecting")
                
                if magic != self.NBD_REQUEST:
                    raise IOError("Bad magic number, disconnecting")
                
                debug1("[%s:%s]: cmd=%s, handle=%s, offset=%s, len=%s\n" % (host, port, cmd, handle, offset, length))
                
                if cmd == self.NBD_CMD_DISC:
                    log("[%s:%s] disconnecting\n" % self.client_address)
                    break
                elif cmd == self.NBD_CMD_WRITE:
                    # or silently ignore them?
                    raise IOError("writing is not supported")
                
                elif cmd == self.NBD_CMD_READ:
                    try:
                        filereader.seek(offset)
                        data = filereader.read(length)
                    except IOError as ex:
                        log("[%s:%s] %s\n" % (host, port, ex))
                        self.nbd_response(self.wfile, handle, error=ex.errno)
                        continue

                    self.nbd_response(self.wfile, handle, data=data)

                elif cmd == self.NBD_CMD_FLUSH:
                    # noop
                    #store.flush()
                    self.nbd_response(self.wfile, handle)

                else:

                    log("[%s:%s] Unknown cmd %s, disconnecting\n" % (host, port, cmd))
                    break

        except IOError as ex:
            log("[%s:%s] %s\n" % (host, port, ex))
        log("exiting client task\n")

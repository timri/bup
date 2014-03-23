#!/usr/bin/env bash
. ./wvtest-bup.sh
. ./t/lib.sh

set -o pipefail

export GIT_AUTHOR_NAME='bup test-get.sh'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_AUTHOR_EMAIL=bup@85430dcca2b611e4b2c3-8f5691723476
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?


bup() { "$top/bup" "$@"; }


reset-bup-dest()
{
    export BUP_DIR=get-dest
    WVPASS rm -rf "$BUP_DIR"
    WVPASS bup init
}


validate-blob()
{
    local src_id="$1"
    local dest_id="$2"
    WVPASS force-delete restore-src restore-dest
    WVPASS "$top/t/git-cat-tree" --git-dir get-src "$src_id" > restore-src
    WVPASS "$top/t/git-cat-tree" --git-dir get-dest "$dest_id" > restore-dest
    WVPASS cmp restore-src restore-dest
}


validate-tree()
{
    local src_id="$1"
    local dest_id="$2"
    WVPASS force-delete restore-src restore-dest
    WVPASS mkdir restore-src restore-dest
    # Tag the trees so the archive contents will have matching timestamps.
    GIT_COMMITTER_DATE="2014-01-01 01:01" \
        WVPASS git --git-dir get-src tag -am '' tmp-src "$src_id"
    GIT_COMMITTER_DATE="2014-01-01 01:01" \
        WVPASS git --git-dir get-dest tag -am '' tmp-dest "$dest_id"
    WVPASS git --git-dir get-src archive tmp-src | tar xf - -C restore-src
    WVPASS git --git-dir get-dest archive tmp-dest | tar xf - -C restore-dest
    # git archive doesn't include an entry for ./.
    WVPASS touch -r restore-src restore-dest
    WVPASS WVPASS git --git-dir get-src tag -d tmp-src
    WVPASS WVPASS git --git-dir get-dest tag -d tmp-dest
    WVPASS "$top/t/compare-trees" -c restore-src/ restore-dest/
    WVPASS force-delete restore-src restore-dest
}


validate-commit()
{
    local src_id="$1"
    local dest_id="$2"
    WVPASS force-delete restore-src restore-dest
    WVPASS git --git-dir get-src cat-file commit "$src_id" > restore-src
    WVPASS git --git-dir get-dest cat-file commit "$dest_id" > restore-dest
    WVPASS cmp restore-src restore-dest
    WVPASS force-delete restore-src restore-dest
    WVPASS mkdir restore-src restore-dest
    WVPASS git --git-dir get-src archive "$src_id" | tar xf - -C restore-src
    WVPASS git --git-dir get-dest archive "$dest_id" | tar xf - -C restore-dest
    # git archive doesn't include an entry for ./.
    WVPASS touch -r restore-src restore-dest
    WVPASS "$top/t/compare-trees" -c restore-src/ restore-dest/
    WVPASS force-delete restore-src restore-dest
}


validate-save()
{
    local orig_dir="$1"
    local save_path="$2"
    local get_log="$3"
    local commit_id="$4"
    local tree_id="$5"

    WVPASS rm -rf restore
    WVPASS bup restore -C restore "$save_path/."
    WVPASS "$top/t/compare-trees" -c "$orig_dir/" restore/
    local orig_git_dir="$GIT_DIR"
    export GIT_DIR="$BUP_DIR"
    if test "$tree_id"; then
        WVPASS git ls-tree "$tree_id"
        WVPASS git cat-file commit "$commit_id" | head -n 1 \
            | WVPASS grep -q "^tree $tree_id\$"
    fi
    if test "$orig_git_dir"; then
        export GIT_DIR="$orig_git_dir"
    else
        unset GIT_DIR
    fi
}


given_count=0
given()
{
    # given() is the core of the bup get testing infrastructure, it
    # handles calls like this:
    #
    #   WVPASS given src-branch \
    #     get save/latest::src-branch" \
    #     produces save obj "$(pwd)/src" "$commit_id" "$tree_id" \
    #     matching ./src-2 \
    #     only-heads src-branch
    #     only-tags ''

    # FIXME: eventually have "fails" test that there was *no* effect
    # on the dest repo?
    # FIXME: add constraints on the branch contents after an operation,
    # i.e. no unexpected commits (might not notice them with new-save for
    # example).  Or perhaps just same-parent or parent HASH for the commit
    # test(s).

    ((given_count++))
    if test "$#" -lt 4; then
        echo "error: too few arguments to given" 1>&2
        exit 1
    fi

    local given_item="$1"
    local get="$2"
    local get_method="$3"
    local item="$4"
    local expectation="$5"
    local get_cmd
    shift 5 # Remaining arguments handled later.

    if test "$get" = get; then
        get_cmd="bup get -vvct --print-tags -s get-src"
    elif test "$get" = get-on; then
        get_cmd="bup on - get -vvct --print-tags -s get-src"
    elif test "$get" = get-to; then
        get_cmd="bup get -vvct --print-tags -s get-src -r -:$(pwd)/get-dest"
    else
        echo "error: unexpected get type $get" 1>&2
        exit 1
    fi

    WVPASS reset-bup-dest
    if test "$given_item" != nothing; then
        WVPASS $get_cmd -vct --print-tags --overwrite "$given_item"
    fi

    if test "$expectation" = fails; then
        $get_cmd "$get_method" "$item"
        local rc=$?
        WVPASS test $rc -eq 97 -o $rc -eq 98
    elif test "$expectation" = complains; then
        if test "$#" -ne 1; then
            WVDIE "error: too few arguments to complains"
        fi
        local expected_err="$1"
        shift
        $get_cmd "$get_method" "$item" 2> >(tee get-stderr.log >&2)
        local rc=$?
        WVPASS test $rc -eq 97 -o $rc -eq 98
        WVPASS grep -E "$expected_err" get-stderr.log
        WVPASS rm get-stderr.log
    elif test "$expectation" = produces; then
        if test "$#" -lt 1; then
            WVDIE "error: too few arguments to produces"
        fi
        WVPASS $get_cmd "$get_method" "$item" | tee get.log
        while test $# -ne 0; do
            local requirement="$1"
            shift
            case "$requirement" in
                only-heads|only-tags)
                    local ref_kind="${requirement:5}"
                    if test "$#" -lt 1; then
                        echo "error: \"produces $requirement\" requires a list of $ref_kind" 1>&2
                        exit 1
                    fi
                    local tmp_names="$1"; shift
                    local tmp_name
                    for tmp_name in $tmp_names; do
                        WVPASS git --git-dir get-dest show-ref "--$ref_kind" "$tmp_name"
                    done
                    local tmp_n="$(echo $tmp_names | tr ' ' '\n' | sort -u | wc -w)" || exit $?
                    WVPASSEQ "$tmp_n" "$(git --git-dir get-dest show-ref -s "--$ref_kind" "$tmp_name" | wc -w)"
                    ;;
                blob|tree|commit)
                    if test "$#" -lt 3; then
                        echo "error: too few arguments to \"produces $requirement\"" 1>&2
                        exit 1
                    fi
                    local dest_name="$1"
                    local comparison="$2"
                    local orig_value="$3"
                    shift 3
                    if test "$comparison" != matching; then
                        WVDIE "error: unrecognized comparison type \"$comparison\""
                    fi
                    validate-"$requirement" "$orig_value" "$dest_name"
                    ;;
                save|new-save)
                    if test "$#" -lt 5; then
                        echo "error: too few arguments to \"produces $requirement\"" 1>&2
                        exit 1
                    fi
                    local dest_name="$1"
                    local restore_subpath="$2"
                    local commit_id="$3"
                    local tree_id="$4"
                    local comparison="$5"
                    local orig_value="$6"
                    shift 6
                    if test "$comparison" != matching; then
                        WVDIE "error: unrecognized comparison type \"$comparison\""
                    fi
                    WVPASSEQ "$(cat get.log | wc -l)" 2
                    local get_tree_id=$(WVPASS awk 'FNR == 1' get.log) || exit $?
                    local get_commit_id=$(WVPASS awk 'FNR == 2' get.log) || exit $?
                    WVPASSEQ "$tree_id" "$get_tree_id"
                    if test "$requirement" = save; then
                        WVPASSEQ "$commit_id" "$get_commit_id"
                        validate-save "$orig_value" "$dest_name$restore_subpath" get.log "$commit_id" "$tree_id" 
                    else
                        WVPASSNE "$commit_id" "$get_commit_id"
                        validate-save "$orig_value" "$dest_name$restore_subpath" get.log "$get_commit_id" "$tree_id" 
                    fi
                    ;;
                tagged-save)
                    if test "$#" -lt 5; then
                        echo "error: too few arguments to \"produces $requirement\"" 1>&2
                        exit 1
                    fi
                    local tag_name="$1"
                    local restore_subpath="$2"
                    local commit_id="$3"
                    local tree_id="$4"
                    local comparison="$5"
                    local orig_value="$6"
                    shift 6
                    if test "$comparison" != matching; then
                        WVDIE "error: unrecognized comparison type \"$comparison\""
                    fi
                    WVPASSEQ "$(cat get.log | wc -l)" 1
                    local get_tag_id=$(WVPASS awk 'FNR == 1' get.log) || exit $?
                    WVPASSEQ "$commit_id" "$get_tag_id"
                    # Make sure tmp doesn't already exist.
                    WVFAIL git --git-dir get-dest show-ref tmp-branch-for-tag
                    WVPASS git --git-dir get-dest branch tmp-branch-for-tag \
                        "refs/tags/$tag_name"
                    validate-save "$orig_value" \
                        "tmp-branch-for-tag/latest$restore_subpath" get.log \
                        "$commit_id" "$tree_id"
                    WVPASS git --git-dir get-dest branch -D tmp-branch-for-tag
                    ;;
                new-tagged-commit)
                    if test "$#" -lt 5; then
                        echo "error: too few arguments to \"produces $requirement\"" 1>&2
                        exit 1
                    fi
                    local tag_name="$1"
                    local commit_id="$2"
                    local comparison="$3"
                    local tree_id="$4"
                    shift 4
                    if test "$comparison" != matching; then
                        WVDIE "error: unrecognized comparison type \"$comparison\""
                    fi
                    WVPASSEQ "$(cat get.log | wc -l)" 1
                    local get_tag_id=$(WVPASS awk 'FNR == 1' get.log) || exit $?
                    WVPASSNE "$commit_id" "$get_tag_id"
                    validate-tree "$tree_id" "$tag_name:"
                    ;;
                *)
                    WVDIE "error: unrecognized produces clause \"$requirement $*\""
                    ;;
            esac
        done
        WVPASS rm get.log
    else
        WVDIE "error: unrecognized expectation \"$expectation $@\""
    fi
    return 0
}


test-universal-behaviors()
{
    local get="$1"
    local methods="--ff --append --pick --force-pick --new-tag --overwrite --unnamed"
    for m in $methods; do
        WVSTART "$get $m, missing source, fails"
        WVPASS given nothing "$get" "$m" not-there complains 'cannot find source'
    done
    for m in $methods; do
        WVSTART "$get $m / fails"
        WVPASS given nothing "$get" "$m" / complains 'cannot fetch entire repository'
    done
}


test-overwrite()
{
    local get="$1"

    WVSTART "$get --overwrite to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path" \
        .tag/subtree "src/latest$subtree_vfs_path" \
        .tag/commit-1 src/latest src
    do
        WVPASS given nothing "$get" --overwrite "$item:/" \
            complains 'impossible; can only overwrite branch or tag'
    done

    # Anything to tag.
    local i=0
    declare -a existing_type=(nothing blob tree commit)
    for existing_tag in nothing .tag/tinyfile:.tag/obj .tag/tree-1:.tag/obj \
        .tag/commit-1:.tag/obj
    do
        WVSTART "$get --overwrite ${existing_type[$i]} with blob tag"
        for item in .tag/tinyfile "src/latest$tinyfile_path"; do
            WVPASS given "$existing_tag" "$get" --overwrite "$item:.tag/obj" \
                produces blob "$tinyfile_id" matching "$tinyfile_id" \
                only-heads '' only-tags obj
        done
        WVSTART "$get --overwrite ${existing_type[$i]} with tree tag"
        for item in .tag/subtree "src/latest$subtree_vfs_path"; do
            WVPASS given "$existing_tag" "$get" --overwrite "$item:.tag/obj" \
                produces tree "$subtree_id" matching "$subtree_id" \
                only-heads '' only-tags obj
        done
        WVSTART "$get --overwrite ${existing_type[$i]} with committish tag"
        for item in .tag/commit-2 src/latest src; do
            WVPASS given "$existing_tag" "$get" --overwrite "$item:.tag/obj" \
                produces tagged-save obj "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
                matching src-2 \
                only-heads '' only-tags obj
        done
        ((i++))
    done

    # Committish to branch.
    local i=0
    declare -a existing_type=(nothing branch)
    declare -a item_type=(commit save branch)
    for existing in nothing .tag/commit-1:obj; do
        local j=0
        for item in .tag/commit-2 src/latest src; do
            WVSTART "$get --overwrite ${existing_type[$i]} with ${item_type[$j]}"
            WVPASS given "$existing" "$get" --overwrite "$item:obj" \
                produces save obj/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
                matching src-2 \
                only-heads obj \
                only-tags ''
            ((j++))
        done
        ((i++))
    done

    # Not committish to branch.
    local i=0
    declare -a existing_type=(nothing branch)
    declare -a item_type=(blob blob tree tree)
    for existing in nothing .tag/commit-1:obj; do
        local j=0
        for item in .tag/tinyfile "src/latest$tinyfile_path" \
            .tag/subtree "src/latest$subtree_vfs_path"
        do
            WVSTART "$get --overwrite branch with ${item_type[$j]} given ${existing_type[$i]} fails"
            WVPASS given "$existing" "$get" --overwrite "$item:obj" \
                complains 'cannot overwrite branch with .+ for'
            ((j++))
        done
        ((i++))
    done

    WVSTART "$get --overwrite, implicit destinations"
    WVPASS given nothing "$get" --overwrite src \
        produces save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src only-tags ''
    WVPASS given nothing "$get" --overwrite .tag/commit-2 \
        produces tagged-save commit-2 "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads '' only-tags commit-2
}


test-ff()
{
    local get="$1"

    WVSTART "$get --ff to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --ff "$item:/" \
            complains 'source for .+ must be a branch, save, or commit'
    done
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" --ff "$item:/" \
            complains 'is impossible; can only --append a tree to a branch'
    done
    for item in .tag/commit-1 src/latest src; do
        WVPASS given nothing "$get" --ff "$item:/" \
            complains 'destination for .+ is a root, not a branch'
    done


    WVSTART "$get --ff of not-committish fails"
    for src in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --ff "$src:obj" \
            complains 'must be a branch, save, or commit'
        WVPASS given nothing "$get" --ff "$src:.tag/obj" \
            complains 'must be a branch, save, or commit'
        WVPASS given .tag/tinyfile:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'must be a branch, save, or commit'
        WVPASS given .tag/tree-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'must be a branch, save, or commit'
        WVPASS given .tag/commit-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'must be a branch, save, or commit'
        WVPASS given .tag/commit-1:obj "$get" --ff "$src:obj" \
            complains 'must be a branch, save, or commit'
    done
    for src in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" --ff "$src:obj" \
            complains 'can only --append a tree to a branch'
        WVPASS given nothing "$get" --ff "$src:.tag/obj" \
            complains 'can only --append a tree to a branch'
        WVPASS given .tag/tinyfile:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'can only --append a tree to a branch'
        WVPASS given .tag/tree-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'can only --append a tree to a branch'
        WVPASS given .tag/commit-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'can only --append a tree to a branch'
        WVPASS given .tag/commit-1:obj "$get" --ff "$src:obj" \
            complains 'can only --append a tree to a branch'
    done

    WVSTART "$get --ff committish, ff possible"
    for src in .tag/commit-2 "src/$src_save2" src; do
        WVPASS given nothing "$get" --ff "$src:.tag/obj" \
            complains 'destination .+ must be a valid branch name'
        WVPASS given .tag/tinyfile:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'destination .+ is a blob, not a branch'
        WVPASS given .tag/tree-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'destination .+ is a tree, not a branch'
        WVPASS given .tag/commit-1:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'destination .+ is a tagged commit, not a branch'
        WVPASS given .tag/commit-2:.tag/obj "$get" --ff "$src:.tag/obj" \
            complains 'destination .+ is a tagged commit, not a branch'
    done
    for src in .tag/commit-2 "src/$src_save2" src; do
        for existing in nothing .tag/commit-1:obj .tag/commit-2:obj; do
            WVPASS given nothing "$get" --ff "$src:obj" \
                produces save obj/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
                matching src-2 \
                only-heads obj \
                only-tags ''
        done
    done

    WVSTART "$get --ff, implicit destinations"
    WVPASS given nothing "$get" --ff src \
        produces save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src \
        only-tags ''
    WVPASS given nothing "$get" --ff src/latest \
        produces save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src \
        only-tags ''

    WVSTART "$get --ff, ff impossible"
    WVPASS given unrelated-branch:src "$get" --ff src \
        complains 'destination is not an ancestor of source'
    WVPASS given .tag/commit-2:src "$get" --ff .tag/commit-1:src \
        complains 'destination is not an ancestor of source'
}


test-append()
{
    local get="$1"

    WVSTART "$get --append to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --append "$item:/" \
            complains 'source for .+ must be a branch, save, commit, or tree'
    done
    for item in .tag/subtree "src/latest$subtree_vfs_path" \
        .tag/commit-1 src/latest src
    do
        WVPASS given nothing "$get" --append "$item:/" \
            complains 'destination for .+ is a root, not a branch'
    done

    WVSTART "$get --append of not-treeish fails"
    for src in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --append "$src:obj" \
            complains 'must be a branch, save, commit, or tree'
        WVPASS given nothing "$get" --append "$src:.tag/obj" \
            complains 'must be a branch, save, commit, or tree'
        WVPASS given .tag/tinyfile:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'must be a branch, save, commit, or tree'
        WVPASS given .tag/tree-1:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'must be a branch, save, commit, or tree'
        WVPASS given .tag/commit-1:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'must be a branch, save, commit, or tree'
        WVPASS given .tag/commit-1:obj "$get" --append "$src:obj" \
            complains 'must be a branch, save, commit, or tree'
    done

    WVSTART "$get --append committish failure cases"
    for src in .tag/subtree "src/latest$subtree_vfs_path" \
        .tag/commit-2 "src/$src_save2" src
    do
        WVPASS given nothing "$get" --append "$src:.tag/obj" \
            complains 'destination .+ must be a valid branch name'
        WVPASS given .tag/tinyfile:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'destination .+ is a blob, not a branch'
        WVPASS given .tag/tree-1:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'destination .+ is a tree, not a branch'
        WVPASS given .tag/commit-1:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'destination .+ is a tagged commit, not a branch'
        WVPASS given .tag/commit-2:.tag/obj "$get" --append "$src:.tag/obj" \
            complains 'destination .+ is a tagged commit, not a branch'
    done

    WVSTART "$get --append committish"
    for item in .tag/commit-2 "src/$src_save2" src; do
        for existing in nothing .tag/commit-1:obj .tag/commit-2:obj unrelated-branch:obj; do
            WVPASS given "$existing" "$get" --append "$item:obj" \
                produces new-save obj/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
                matching src-2 \
                only-heads obj \
                only-tags ''
        done
    done
    # Append ancestor.
    for item in .tag/commit-1 "src/$src_save1" src-1; do
        WVPASS given .tag/commit-2:obj "$get" --append "$item:obj" \
            produces new-save obj/latest "$(pwd)/src" "$src_commit1_id" "$src_tree1_id" \
            matching src-1 \
            only-heads obj \
            only-tags ''
    done

    WVSTART "$get --append tree"
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        for existing in nothing .tag/commit-1:obj .tag/commit-2:obj; do
            WVPASS given nothing "$get" --append "$item:obj" \
                produces new-save obj/latest "/" IRRELEVANT "$subtree_id" \
                matching "$subtree_path" \
                only-heads obj \
                only-tags ''
        done
    done

    WVSTART "$get --append, implicit destinations"
    WVPASS given nothing "$get" --append src \
        produces new-save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src \
        only-tags ''
    WVPASS given nothing "$get" --append src/latest \
        produces new-save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src \
        only-tags ''
}


test-pick()
{
    local get="$1"
    local pick="$2"

    WVSTART "$get $pick to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path" src; do
        WVPASS given nothing "$get" "$pick" "$item:/" \
            complains 'can only pick a commit or save'
    done
    for item in .tag/commit-1 src/latest; do
        WVPASS given nothing "$get" "$pick" "$item:/" \
            complains 'destination is not a tag or branch'
    done
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" "$pick" "$item:/" \
            complains 'is impossible; can only --append a tree'
    done

    WVSTART "$get $pick of blob or branch fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path" src; do
        WVPASS given nothing "$get" "$pick" "$item:obj" \
            complains 'impossible; can only pick a commit or save'
        WVPASS given nothing "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only pick a commit or save'
        WVPASS given .tag/tinyfile:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only pick a commit or save'
        WVPASS given .tag/tree-1:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only pick a commit or save'
        WVPASS given .tag/commit-1:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only pick a commit or save'
        WVPASS given .tag/commit-1:obj "$get" "$pick" "$item:obj" \
            complains 'impossible; can only pick a commit or save'
    done

    WVSTART "$get $pick of tree fails"
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" "$pick" "$item:obj" \
            complains 'impossible; can only --append a tree'
        WVPASS given nothing "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only --append a tree'
        WVPASS given .tag/tinyfile:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only --append a tree'
        WVPASS given .tag/tree-1:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only --append a tree'
        WVPASS given .tag/commit-1:.tag/obj "$get" "$pick" "$item:.tag/obj" \
            complains 'impossible; can only --append a tree'
        WVPASS given .tag/commit-1:obj "$get" "$pick" "$item:obj" \
            complains 'impossible; can only --append a tree'
    done

    if test "$pick" = --pick; then
        WVSTART "$get $pick commit/save to existing tag fails"
        for item in .tag/commit-2 "src/$src_save2"; do
            for existing in .tag/tinyfile:.tag/obj .tag/tree-1:.tag/obj \
                .tag/commit-1:.tag/obj
            do
                WVPASS given "$existing" "$get" "$pick" "$item:.tag/obj" \
                    complains 'cannot overwrite existing tag'
            done
        done
    else  # --force-pick
        WVSTART "$get $pick commit/save to existing tag"
        for item in .tag/commit-2 "src/$src_save2"; do
            for existing in .tag/tinyfile:.tag/obj .tag/tree-1:.tag/obj \
                .tag/commit-1:.tag/obj
            do
                WVPASS given "$existing" "$get" "$pick" "$item:.tag/obj" \
                    produces new-tagged-commit obj "$src_commit2_id" \
                    matching "$src_tree2_id" \
                    only-heads '' only-tags obj
            done
        done
    fi

    WVSTART "$get $pick commit/save to tag"
    for item in .tag/commit-2 "src/$src_save2"; do
        WVPASS given nothing "$get" "$pick" "$item:.tag/obj" \
            produces new-tagged-commit obj "$src_commit2_id" \
            matching "$src_tree2_id" \
            only-heads '' only-tags obj
    done

    WVSTART "$get $pick commit/save to branch"
    for item in .tag/commit-2 "src/$src_save2"; do
        for existing in nothing .tag/commit-1:obj .tag/commit-2:obj; do
            WVPASS given "$existing" "$get" "$pick" "$item:obj" \
                produces new-save obj/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
                matching src-2 \
                only-heads obj \
                only-tags ''
        done
    done

    WVSTART "$get $pick commit/save unrelated commit to branch"
    for item in .tag/commit-2 "src/$src_save2"; do
        WVPASS given unrelated-branch:obj "$get" "$pick" "$item:obj" \
            produces new-save obj/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
            matching src-2 \
            only-heads obj \
            only-tags ''
    done

    WVSTART "$get $pick commit/save ancestor to branch"
    for item in .tag/commit-1 "src/$src_save1"; do
        WVPASS given .tag/commit-2:obj "$get" "$pick" "$item:obj" \
            produces new-save obj/latest "$(pwd)/src" "$src_commit1_id" "$src_tree1_id" \
            matching src-1 \
            only-heads obj \
            only-tags ''
    done

    WVSTART "$get $pick, implicit destinations"
    WVPASS given nothing "$get" "$pick" .tag/commit-2 \
        produces new-tagged-commit commit-2 "$src_commit2_id" \
        matching "$src_tree2_id" \
        only-heads '' \
        only-tags commit-2
    WVPASS given nothing "$get" "$pick" src/latest \
        produces new-save src/latest "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads src \
        only-tags ''
}


test-new-tag()
{
    local get="$1"

    WVSTART "$get --new-tag to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path" \
        .tag/subtree "src/latest$subtree_vfs_path" \
        .tag/commit-1 src/latest src
    do
        WVPASS given nothing "$get" --new-tag "$item:/" \
            complains 'destination for .+ must be a VFS tag'
    done

    # Anything to new tag.
    WVSTART "$get --new-tag, blob tag"
    for item in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --new-tag "$item:.tag/obj" \
            produces blob "$tinyfile_id" matching "$tinyfile_id" \
            only-heads '' only-tags obj
    done
    WVSTART "$get --new-tag, tree tag"
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" --new-tag "$item:.tag/obj" \
            produces tree "$subtree_id" matching "$subtree_id" \
            only-heads '' only-tags obj
    done
    WVSTART "$get --new-tag, committish tag"
    for item in .tag/commit-2 src/latest src; do
        WVPASS given nothing "$get" --new-tag "$item:.tag/obj" \
            produces tagged-save obj "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
            matching src-2 \
            only-heads '' only-tags obj
    done

    # Anything to existing tag (fails).
    local i=0
    declare -a existing_type=(blob tree commit)
    declare -a item_type=(blob blob tree tree commit save branch)
    for existing_tag in .tag/tinyfile:.tag/obj .tag/tree-1:.tag/obj \
        .tag/commit-1:.tag/obj
    do
        local j=0
        for item in .tag/tinyfile "src/latest$tinyfile_path" \
            .tag/subtree "src/latest$subtree_vfs_path" \
            .tag/commit-2 src/latest src
        do
            WVSTART "$get --new-tag, ${item_type[$j]} tag, given existing ${existing_type[$i]} fails"
            WVPASS given "$existing_tag" "$get" --new-tag "$item:.tag/obj" \
                complains 'cannot overwrite existing tag .* \(requires --overwrite\)'
            ((j++))
        done
        ((i++))
    done

    # Anything to branch (fails).
    local i=0
    declare -a existing_type=(nothing blob tree commit)
    declare -a item_type=(blob blob tree tree commit save branch)
    for existing_tag in nothing .tag/tinyfile:.tag/obj .tag/tree-1:.tag/obj \
        .tag/commit-1:.tag/obj
    do
        local j=0
        for item in .tag/tinyfile "src/latest$tinyfile_path" \
            .tag/subtree "src/latest$subtree_vfs_path" \
            .tag/commit-2 src/latest src
        do
            WVSTART "$get --new-tag, ${item_type[$j]} branch, given existing ${existing_type[$i]} fails"
            WVPASS given "$existing_tag" "$get" --new-tag "$item:obj" \
                complains 'destination for .+ must be a VFS tag'
            ((j++))
        done
        ((i++))
    done

    WVSTART "$get --new-tag, implicit destinations"
    WVPASS given nothing "$get" --new-tag .tag/commit-2 \
        produces tagged-save commit-2 "$(pwd)/src" "$src_commit2_id" "$src_tree2_id" \
        matching src-2 \
        only-heads '' only-tags commit-2
}


test-unnamed()
{
    local get="$1"

    WVSTART "$get --unnamed to root fails"
    for item in .tag/tinyfile "src/latest$tinyfile_path" \
        .tag/subtree "src/latest$subtree_vfs_path" .tag/commit-1 src/latest src
    do
        WVPASS given nothing "$get" --unnamed "$item:/" \
            complains 'destination name given'
        WVPASS given "$item:.tag/obj" "$get" --unnamed "$item:/" \
            complains 'destination name given'
    done

    WVSTART "$get --unnamed file"
    for item in .tag/tinyfile "src/latest$tinyfile_path"; do
        WVPASS given nothing "$get" --unnamed "$item" \
            produces blob "$tinyfile_id" matching "$tinyfile_id" \
            only-heads '' only-tags ''
        WVPASS given "$item:.tag/obj" "$get" --unnamed "$item" \
            produces blob "$tinyfile_id" matching "$tinyfile_id" \
            only-heads '' only-tags 'obj'
    done

    WVSTART "$get --unnamed tree"
    for item in .tag/subtree "src/latest$subtree_vfs_path"; do
        WVPASS given nothing "$get" --unnamed "$item" \
            produces tree "$subtree_id" matching "$subtree_id" \
            only-heads '' only-tags ''
        WVPASS given "$item:.tag/obj" "$get" --unnamed "$item" \
            produces tree "$subtree_id" matching "$subtree_id" \
            only-heads '' only-tags 'obj'
    done

    WVSTART "$get --unnamed committish"
    for item in .tag/commit-2 "src/$src_save2" src; do
        WVPASS given nothing "$get" --unnamed "$item" \
            produces commit "$src_commit2_id" matching "$src_commit2_id" \
            only-heads '' only-tags ''
        WVPASS given "$item:.tag/obj" "$get" --unnamed "$item" \
            produces commit "$src_commit2_id" matching "$src_commit2_id" \
            only-heads '' only-tags 'obj'
    done
}


# Setup.
WVPASS cd "$tmpdir"
export BUP_DIR=get-src
WVPASS bup init

WVPASS mkdir src
WVPASS touch src/unrelated
WVPASS bup index src
WVPASS bup save -tcn unrelated-branch src

WVPASS bup index --clear
WVPASS rm -r src
WVPASS mkdir src
WVPASS touch src/zero
WVPASS bup index src
WVPASS bup save -tcn src src | tee save-output.log
src_tree0_id=$(WVPASS head -n 1 save-output.log) || exit $?
src_commit0_id=$(WVPASS tail -n -1 save-output.log) || exit $?
src_save0=$(WVPASS bup ls src | WVPASS awk 'FNR == 1') || exit $?
WVPASS git --git-dir get-src branch src-0 src
WVPASS cp -a src src-0

WVPASS rm -r src
WVPASS mkdir src src/x src/x/y
WVPASS bup random 1k > src/1
WVPASS bup random 1k > src/x/2
WVPASS bup index src
WVPASS bup save -tcn src src | tee save-output.log
src_tree1_id=$(WVPASS head -n 1 save-output.log) || exit $?
src_commit1_id=$(WVPASS tail -n -1 save-output.log) || exit $?
src_save1=$(WVPASS bup ls src | WVPASS awk 'FNR == 2') || exit $?
WVPASS git --git-dir get-src branch src-1 src
WVPASS cp -a src src-1

# Make a copy the current state of src so we'll have an ancestor.
cp -a get-src/refs/heads/src get-src/refs/heads/src-ancestor

WVPASS echo -n 'xyzzy' > src/tiny-file
WVPASS bup index src
WVPASS bup tick # Make sure the save names are different.
WVPASS bup save -tcn src src | tee save-output.log
src_tree2_id=$(WVPASS head -n 1 save-output.log) || exit $?
src_commit2_id=$(WVPASS tail -n -1 save-output.log) || exit $?
src_save2=$(WVPASS bup ls src | WVPASS awk 'FNR == 3') || exit $?
WVPASS mv src src-2

src_root="$(pwd)/src"

subtree_path=src-2/x
subtree_vfs_path="$src_root/x"
# No support for "ls -d", so grep...
subtree_id=$(WVPASS bup ls -s "src/latest$src_root" | WVPASS grep x \
    | WVPASS cut -d' ' -f 1) || exit $?

# With a tiny file, we'll get a single blob, not a chunked tree.
tinyfile_path="$src_root/tiny-file"
tinyfile_id=$(WVPASS bup ls -s "src/latest$tinyfile_path" \
    | WVPASS cut -d' ' -f 1) || exit $?

WVPASS bup tag tinyfile "$tinyfile_id"
WVPASS bup tag subtree "$subtree_id"
WVPASS bup tag tree-0 "$src_tree0_id"
WVPASS bup tag tree-1 "$src_tree1_id"
WVPASS bup tag tree-2 "$src_tree2_id"
WVPASS bup tag commit-0 "$src_commit0_id"
WVPASS bup tag commit-1 "$src_commit1_id"
WVPASS bup tag commit-2 "$src_commit2_id"
WVPASS git --git-dir="$BUP_DIR"  branch commit-1 "$src_commit1_id"
WVPASS git --git-dir="$BUP_DIR"  branch commit-2 "$src_commit2_id"

# FIXME: this fails in a strange way:
#   WVPASS given nothing get --ff not-there

get_directions=get

if test "$BUP_TEST_LEVEL" = 11; then
    get_directions='get get-on get-to'
fi

for get in $get_directions; do
    # "given FOO" depends on --overwrite, so test it early.
    test-overwrite "$get"
    test-universal-behaviors "$get"
    test-ff "$get"
    test-append "$get"
    test-pick "$get" --pick
    test-pick "$get" --force-pick
    test-new-tag "$get"
    test-unnamed "$get"
done

WVSTART "checked $given_count cases"

WVPASS rm -rf "$tmpdir"

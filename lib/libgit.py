#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

#
# Python Git library
#
import os
import repo
from git import *

def quote_string(s):
    s = s.replace('\"', '\\\"')
    return '\"%s\"' % s


def tree(branch, recursive = False, root = None):
    # initialize tree
    if not tree:
        root = Repo().heads[branch].commit.tree
    if not root:
        return []
    objs = [(x.mode, x.type, x.hexsha, x.path) for x in root.blobs]
    if recursive and root.trees:
        for t in root.trees:
            objs.extend(tree(branch, recursive=True, root=t))
    return objs


def cat_file(sha):
    return command_lines('cat-file', [ '-p', sha ])

def change_head_branch(branch):
    return command_lines('symbolic-ref', ['HEAD', 'refs/heads/%s' % branch])

def command_lines(subcmd, opts = [], from_root=False, explicit_git_dir=False):
    explicit_git_dir_str = ''
    if explicit_git_dir:
        git_dir = command_lines('rev-parse', ['--git-dir'], False)[0]
        explicit_git_dir_str = '--git-dir=%s ' % git_dir
    if from_root:
        cwd = os.getcwd()
        os.chdir(repo.find_root())
    cmd = 'git %s%s %s' % (explicit_git_dir_str, subcmd, ' '.join(map(quote_string, opts)))
    output = os.popen(cmd).read()
    if from_root:
        os.chdir(cwd)
    if output.endswith(os.linesep):
        output = output[:-len(os.linesep)]
    return output.split(os.linesep)

def command_exitcode_only(subcmd, opts = [], from_root=False, explicit_git_dir=False):
    explicit_git_dir_str = ''
    if explicit_git_dir:
        git_dir = command_lines('rev-parse', ['--git-dir'], False)[0]
        explicit_git_dir_str = '--git-dir=%s ' % git_dir
    if from_root:
        cwd = os.getcwd()
        os.chdir(repo.find_root())
    cmd = 'git %s%s %s' % (explicit_git_dir_str, subcmd, ' '.join(map(quote_string, opts)))
    p = os.popen(cmd)
    exitcode = p.close()
    if from_root:
        os.chdir(cwd)
    if exitcode is None:
        exitcode = 0
    return exitcode

def has_unstaged_changes():
    exitcode = command_exitcode_only( \
        'diff',  \
        ['--no-ext-diff','--ignore-submodules','--quiet','--exit-code'])
    return exitcode != 0

def has_uncommitted_changes():
    exitcode = command_exitcode_only( \
        'diff-index',  \
        ['--cached','--quiet','--ignore-submodules','HEAD','--'])
    return exitcode != 0

if __name__ == '__main__':
    print tree(Repo().active_branch.name, recursive=True)
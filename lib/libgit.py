#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

#
# Python Git library
#
import os
from git import *

def quote_string(s):
    s = s.replace('\"', '\\\"')
    return '\"%s\"' % s


def command_lines(subcmd, opts = [], from_root=False, explicit_git_dir=False):
    explicit_git_dir_str = ''
    if explicit_git_dir:
        git_dir = command_lines('rev-parse', ['--git-dir'], False)[0]
        explicit_git_dir_str = '--git-dir=%s ' % git_dir
    if from_root:
        cwd = os.getcwd()
        os.chdir(Repo().working_dir)
    cmd = 'git %s%s %s' % (explicit_git_dir_str, subcmd, ' '.join(map(quote_string, opts)))
    output = os.popen(cmd).read()
    if from_root:
        os.chdir(cwd)
    if output.endswith(os.linesep):
        output = output[:-len(os.linesep)]
    return output.split(os.linesep)

if __name__ == '__main__':
    print tree(Repo().active_branch.name, recursive=True)

#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

import os

def find_root():
    cwd = os.getcwd()
    while cwd != '/':
        gitrepo = cwd + '/.git'
        if os.path.isdir(gitrepo):
            return cwd
        cwd = os.path.abspath(cwd + '/..')
    return None


def find_git_repo():
    cwd = os.getcwd()
    while cwd != '/':
        gitrepo = cwd + '/.git'
        if os.path.isdir(gitrepo):
            return gitrepo
        cwd = os.path.abspath(cwd + '/..')
    return None


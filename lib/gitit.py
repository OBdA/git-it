#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

import sys, os, re
import datetime
from tempfile import mkstemp
import misc, log, ticket, it

from git import *

# Backward-compatible import of SHA1 en MD5 hash algoritms
try:
    import hashlib
    md5_constructor  = hashlib.md5
    sha1_constructor = hashlib.sha1
except ImportError:
    import md5
    md5_constructor = md5.new
    import sha
    sha1_constructor = sha.new


def cmp_by_prio_then_date(ticket1, ticket2):
    v = ticket1.cmp_by(ticket2, 'priority')
    if v == 0:
        v =  ticket1.cmp_by(ticket2, 'created')
    return v


def versionCmp(strx, stry):
    pattern = '^([^0-9]*)([0-9]*)(.*)$'
    matchx = re.match(pattern, strx)
    matchy = re.match(pattern, stry)
    if matchx is None or matchy is None:
        return 0

    prefixx, valuex, restx = matchx.groups()
    prefixy, valuey, resty = matchy.groups()
    if valuex == valuey:
        if valuex == '':
            return 0
        else:
            return versionCmp(restx, resty)

    # Missing left-hand
    if valuex == '':
        return -1
    elif valuey == '':
        return 1

    # Compare x to y
    x = int(valuex)
    y = int(valuey)
    return cmp(x, y)


def cmp_by_release_dir(dir1, dir2):
    _, _, _, title1 = dir1
    _, _, _, title2 = dir2
    if title1 ==  it.UNCATEGORIZED:
        return -1
    elif title2 == it.UNCATEGORIZED:
        return 1
    else:
        return -versionCmp(title1, title2)


class Gitit:
    def __init__(self):
        try:
            self.repo = Repo()
        except InvalidGitRepositoryError:
            log.printerr("Not a valid Git repository.")
            sys.exit(1)

        self.itdb_tree = None
        try:
            self.itdb_tree = self.repo.heads[it.ITDB_BRANCH] \
                    .commit.tree[it.TICKET_DIR]
        except IndexError:
            pass

        # get config reader direct from git.Repo()
        self._gitcfg = self.repo.config_reader()


    def get_cfg(self, key, section='core', default=None):
        value = default
        try:
            value = self._gitcfg.get(section, key)
        except NoSectionError as e:
            log.printerr("%s: No such git config section: %s" % (section, e))

        except NoOptionError:
            log.printerr("%s: No such key in git config section '%s': %s" % (key, section, e))
        return value


    def itdb_exists(self, with_remotes=False):
        if with_remotes:
            branches = [it.ITDB_BRANCH, 'remotes/origin/' + it.ITDB_BRANCH, None]
        else:
            branches = [it.ITDB_BRANCH, None]

        for branch in branches:
            if branch in [b.name for b in self.repo.branches]:
                break
        if branch == None:
            return False

        # look for the hold file in the file list
        abs_hold_file = os.path.join(it.TICKET_DIR, it.HOLD_FILE)
        ls = [x.path for x in self.itdb_tree.list_traverse(depth=1)]
        if abs_hold_file in ls:
            return True
        return False


    def require_itdb(self):
        """
        This method asserts that the itdb is initialized, or errors if not.
        """
        if not self.itdb_exists():
            log.printerr("The itdb is not yet initialized.\n" \
                    + "Run 'it init' first to create a new itdb.")
            sys.exit(1)


    def init(self):
        """ Initializes a ITDB if it does not exists. Otherwise search for
            a remote ITDB an branch from it.
        """
        # check wheter it is already initialzed
        if it.ITDB_BRANCH in [b.name for b in self.repo.branches]:
            # check for the hold file
            abs_hold_file = os.path.join(it.TICKET_DIR, it.HOLD_FILE)
            if abs_hold_file in [x.path for x in self.itdb_tree.list_traverse(depth=1)]:
                print("Issue database already initialized.")
                return

        # search for a ITDB on a remote branch
        for r in self.repo.remotes:
            for ref in r.refs:
                if ref.name.endswith(it.ITDB_BRANCH):
                    print("Initialize ticket database from %s." % ref.name)
                    self.repo.create_head( 'refs/heads/%s'%it.ITDB_BRANCH, ref.name)
                    return

        # else, initialize the new .it database alongside the .git repo
        gitrepo = self.repo.git_dir
        if not gitrepo:
            log.printerr("%s: Not a valid Git repository." % gitrepo)
            return

        #FIXME: use working_dir directly instead of assuming 'git_repo'
        #       is work_dir/.git
        parent, _ = os.path.split(gitrepo)
        ticket_dir = os.path.join(parent, it.TICKET_DIR)
        hold_file = os.path.join(ticket_dir, it.HOLD_FILE)
        curr_branch = self.repo.active_branch.name
        msg = "Initialized empty ticket database."
        abs_ticket_dir = os.path.join( self.repo.working_dir, it.TICKET_DIR)
        try:
            misc.mkdirs(ticket_dir)
            misc.write_file_contents(hold_file, \
                         'This is merely a placeholder file for git-it that prevents ' + \
                         'this directory from\nbeing pruned by Git.')

            # Commit the new itdb to the repo
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            self.repo.git.add([hold_file])
            self.repo.git.commit(['-m', msg, hold_file])
            print("Initialized empty ticket database.")
        except Exception:
            log.printerr("Error initialising ticket database.")

        finally:
            os.remove(hold_file)
            os.rmdir(ticket_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)


    def match_or_error(self, sha):
        """ Returns relative path to ticket
        """
        self.require_itdb()

        matches = []
        for path in [x.path for x in self.itdb_tree.list_traverse()]:
            _, file = os.path.split(path)
            if file.startswith(sha):
                matches.append(path)

        if len(matches) == 0:
            log.printerr("No such ticket")
            sys.exit(1)
        elif len(matches) > 1:
            log.printerr("Ambiguous match criteria. The following tickets match:")
            for match in matches:
                _, id = os.path.split(match)
                log.printerr(id)
            sys.exit(1)
        else:
            return matches[0]


    def edit(self, sha):
        i, rel, fullsha, match = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)

        # Save the contents of this ticket to a file, so it can be edited
        fd, filename = mkstemp(prefix='git-it.')
        # update last_modified now, because later we have to edit the ticket
        # file itself
        i.update_last_modified()
        i.save(filename)
        timestamp1 = os.path.getmtime(filename)
        edit_cmd = self.get_cfg('editor', default='vim') + ' "%s"'
        success = os.system(
                edit_cmd % filename
        ) == 0
        timestamp2 = os.path.getmtime(filename)
        if not success:
            log.printerr("Editing of ticket '%s' failed" % sha7)
            os.remove(filename)
            sys.exit(1)

        if timestamp1 >= timestamp2:
            print("Editing of ticket '%s' cancelled" % sha7)
            os.remove(filename)
            return

        try:
            with open(filename) as fd:
                i = ticket.NewTicket(fd)

        except ticket.MalformedTicketFieldException as e:
            log.printerr("Error parsing ticket: %s" % e)
            sys.exit(1)
        except ticket.MissingTicketFieldException as e:
            log.printerr("Error parsing ticket: %s" % e)
            sys.exit(1)

        # compatibility with git-it <= 0.2
        i.set_default('id', fullsha)
        i.set_default('release', rel)

        # Now, when the edit has succesfully taken place, switch branches, commit,
        # and switch back
        curr_branch = self.repo.active_branch.name
        msg = "Ticket '%s' edited" % sha7
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)
        try:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            i.save()
            self.repo.git.commit(['-m', msg, i.filename])
            print("Ticket '%s' edited succesfully" % sha7)
        except Exception as ex:
            raise RuntimeError("Error commiting modified ticket: %s", ex)

        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)

        # Remove the temporary file
        os.remove(filename)


    def mv(self, sha, to_rel):
        self.require_itdb()
        i, rel, fullsha, src_path = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)

        src_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR, rel)
        target_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR, to_rel)
        target_path = os.path.join(target_dir, fullsha)
        if src_dir == target_dir:
            log.printerr("Ticket '%s' already in '%s'" % (sha7, to_rel))
            return

        # Create the target dir, if neccessary
        if not os.path.isdir(target_dir):
            misc.mkdirs(target_dir)

        # Try to move the file into it
        curr_branch = self.repo.active_branch.name
        msg = "Moved ticket '%s' (%s --> %s)" % (sha7, rel, to_rel)
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)
        rc = 0  # our return value
        try:
            # Commit the new itdb to the repo
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])

            i.data['release'] = to_rel
            i.save(target_path)
            if os.path.isfile(src_path):
                os.remove(src_path)

            self.repo.git.add([target_path])
            self.repo.git.commit(['-m', msg, src_path, target_path])
            print("Ticket '%s' moved to release '%s'" % (sha7, to_rel))
        except OSError as e:
            log.printerr("Could not move ticket '%s' to '%s':" % (sha7, to_rel))
            log.printerr(e)
            rc = 1
        except Exception:
            log.printerr("Could not move ticket '%s' to '%s':" % (sha7, to_rel))
            rc = 1
        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)

        return rc


    def show(self, sha):
        i, _, _, _ = self.get_ticket(sha)
        i.print_ticket()


    def sync(self):
        # check whether this working tree has unstaged/uncommitted changes
        # in order to prevent data loss from happening
        if self.repo.is_dirty(index=False):
            print("Current working tree has unstaged changes. Aborting.")
            sys.exit(1)
        if self.repo.is_dirty():
            print("Current working tree has uncommitted changes. Aborting.")
            sys.exit(1)

        remote = 'origin'
        remote_path = remote +'/'+ it.ITDB_BRANCH

        try:
            # check we have a remote branch available
            if remote_path not in [x.name for x in self.repo.remotes[remote].refs]:
                print("No remote branch to pull from '%s'" % remote_path)
                return
        except AssertionError as e:
            print("No remote branch for '%s'" % remote_path)
            return

        # now we may sync the git-it branch safely!
        curr = self.repo.active_branch.name
        try:
            self.repo.git.checkout([it.ITDB_BRANCH])
            self.repo.remotes[remote].pull()
            self.repo.remotes[remote].push()
        except Exception as e:
            log.printerr("Error pulling/pushing to ticket database: %s" % e)
        finally:
            self.repo.git.checkout([curr])


    def new(self):
        self.require_itdb()

        # Create a fresh ticket
        try:
            i = ticket.NewTicket()
        except KeyboardInterrupt:
            print('')
            print("Aborting new ticket.")
            return None

        # Save the ticket to disk
        i.save()
        sha7 = misc.chop(i.data['id'], 7)
        print("New ticket '%s' saved" % sha7)

        # Commit the new ticket to the 'git-it' branch
        curr_branch = self.repo.active_branch.name
        msg = "%s added ticket '%s'" % (i.data['issuer'], sha7)
        msg = msg.capitalize()
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        try:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            self.repo.git.add([i.filename])
            self.repo.git.commit(['-m', msg, i.filename])
        except:
            log.printerr("Error commiting changes to ticket '%s'" % sha7)
        finally:
            os.remove(i.filename)
            self.repo.git.rm(['--cached', i.filename])
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
        return i


    def progress_bar(self, percentage_done, width = 32):
        blocks_done = int(percentage_done * 1.0 * width)
        # colored: '[' <black-on-green>string_done<default>] '] ' percentage '%'
        format_string_done = ''.join(['>' for i in range(blocks_done)])
        format_string_togo = ('%%-%ds' % (width - blocks_done)) % ''
        return ''.join(['[', format_string_done, format_string_togo, '] %d%%' \
                % int(percentage_done * 100)])


    def __print_ticket_rows(self, rel, tickets, show_types, show_progress_bar, annotate_ownership):
        print_count = 0

        # Get the available terminal drawing space
        width = 80
        try:
            width, _ = os.get_terminal_size()
        except Exception as e:
            #logging.warning("os.get_terminal_size failed: %s", e)
            print("os.get_terminal_size failed: %s" % e)
            try:
                _, width = os.popen('stty size').read().strip().split()
                width = int(width)
            except ValueError as e:
                #logging.error("Can not get the available width -- take %d", width)
                print("Can not get the available width -- take %d" % width)
                pass

        total = sum([t.data['weight'] for t in tickets if t.data['status'] != 'rejected']) * 1.0
        done = sum([t.data['weight'] for t in tickets if t.data['status'] not in ['open', 'rejected', 'test']]) * 1.0
        # colored: <red-on-white> rel <default>
        release_line = '%-16s' % rel

        # Show a progress bar only when there are items in this release
        if total > 0 and show_progress_bar:
            header = release_line + self.progress_bar(done / total)
        else:
            header = release_line

        # First, filter all types that do not need to be shown out of the list
        tickets_to_print = filter(lambda t: t.data['status'] in show_types, tickets)
        if len(tickets_to_print) > 0:
            print(header)

            # Then, sort the tickets by date modified
            tickets_to_print.sort(cmp_by_prio_then_date)

            # ...and finally, print them
            hide_status = show_types == [ 'open' ]
            cols = [ { 'id': 'id',     'width':  7, 'visible': True },
                     { 'id': 'type',   'width':  7, 'visible': True },
                     { 'id': 'title',  'width':  0, 'visible': True },
                     { 'id': 'wght',   'width':  5, 'visible': not hide_status },
                     { 'id': 'status', 'width':  8, 'visible': not hide_status },
                     { 'id': 'date',   'width': 10, 'visible': True },
                     { 'id': 'prio',   'width':  4, 'visible': True },
                   ]

            # Calculate the real value for the zero-width column
            # Assumption here is that there is only 1 zero-width column
            visible_colwidths = map(lambda c: c['width'], filter(lambda c: c['visible'], cols))
            total_width = sum(visible_colwidths) + len(visible_colwidths)
            for col in cols:
                if col['width'] == 0:
                    col['width'] = max(0, width - total_width)

            colstrings = []
            for col in cols:
                if not col['visible']:
                    continue
                colstrings.append(misc.pad_to_length(col['id'], col['width']))

            # colored: <blue-on-white> ' '.join(colstrings) <default>
            print(' '.join(colstrings))

            for t in tickets_to_print:
                print_count += 1
                print(t.oneline(cols, annotate_ownership))

            print('')
        else:
            pass

        return print_count


    def list(self, show_types = ['open', 'test'], releases_filter = []):
        self.require_itdb()
        base_tree = self.repo.heads[it.ITDB_BRANCH].commit.tree[it.TICKET_DIR]
        releasedirs = [(x.mode, x.type, x.hexsha, x.name) for x in base_tree.trees]

        # Filter releases
        if releases_filter:
            filtered = []
            for dir in releasedirs:
                _, _, _, name = dir
                if name in releases_filter:
                    filtered.append(dir)
            releasedirs = filtered

        # Show message if no tickets there
        if len(releasedirs) == 0:
            print("No tickets yet. Use 'it new' to add new tickets.")
            return

        # Collect tickets assigned to self on the way
        inbox = []

        print_count = 0
        releasedirs.sort(cmp_by_release_dir)
        fullname = self.get_cfg('name', section='user', default='Anonymous')
        for _, _, sha, rel in releasedirs:
            rel_tree = self.repo.heads[it.ITDB_BRANCH].commit.tree[it.TICKET_DIR]
            for dir in rel.split('/'):
                rel_tree = rel_tree[dir]
            ticketfiles = [(x.mode, x.type, x.hexsha, x.name) for x in rel_tree.blobs]

            #FIXME: do not use 'ticket_id' and 'release' in ticket constructor
            #       Backward compatibility only!
            tickets = [ ticket.NewTicket(
                    self.repo.git.cat_file(['-p', sha]).split("\n"),
                    ticket_id=ticket_id, release=rel
                ) for _, type, sha, ticket_id in ticketfiles \
                if type == 'blob' and ticket_id != it.HOLD_FILE \
            ]

            # Store the tickets in the inbox if neccessary
            inbox += filter(lambda t: t.is_assigned_to(fullname), tickets)

            print_count += self.__print_ticket_rows(rel, tickets, show_types, True, True)

        print_count += self.__print_ticket_rows('INBOX', inbox, (show_types == ['open','test']) and ['open'] or show_types, False, False)

        if print_count == 0:
            print("Use the -a flag to show all tickets")


    def rm(self, sha):
        match = self.match_or_error(sha)
        print("Remove permanently '%s'" % match)
        print("(Press CTRL-C to abort...)")
        try:
            raw_input()
        except KeyboardInterrupt:
            log.printerr("Abort!")
            sys.exit(1)

        _, basename = os.path.split(match)
        sha7 = misc.chop(basename, 7)

        # prepare the critical section
        curr_branch = self.repo.active_branch.name
        curr_dir = os.getcwd()
        msg = "Removed ticket '%s'" % sha7
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        # Commit the new itdb to the repo
        try:
            os.chdir(self.repo.working_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            self.repo.git.commit(['-m', msg, match])
            print("ticket '%s' removed" % sha7)
        except Exception:
            log.printerr("Error commiting change!")
            sys.exit(1)
        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
            os.chdir(curr_dir)


    def get_ticket(self, sha):
        match = self.match_or_error(sha)
        parent, fullsha = os.path.split(match)
        rel = os.path.basename(parent)

        contents = self.repo.git.cat_file(['-p', it.ITDB_BRANCH + ':' + match])
        i = ticket.NewTicket(contents.split("\n"), ticket_id=fullsha, release=rel)
        #FIXME: do only return the ticket, not a tuple of ticket particles
        return (i, i.data['release'], i.data['id'], match)


    def finish_ticket(self, sha, new_status):
        i, _, fullsha, match = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)
        if i.data['status'] not in ['open', 'test']:
            log.printerr("Ticket '%s' already %s" % (sha7, i.data['status']))
            sys.exit(1)

        # Now, when the edit has succesfully taken place, switch branches, commit,
        # and switch back
        curr_branch = self.repo.active_branch.name
        curr_dir = os.getcwd()
        msg = "%s ticket '%s'" % (i.data['status'], sha7)
        msg = msg.capitalize()
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        try:
            os.chdir(self.repo.working_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            i.data['status'] = new_status
            i.save()
            self.repo.git.commit(['-m', msg, match])
            print("Ticket '%s' now %s" % (sha7, new_status))
        except Exception:
            log.printerr("Error commiting changes to ticket '%s'" % sha7)
        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
            os.chdir(curr_dir)


    def reopen_ticket(self, sha):
        i, _, fullsha, match = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)
        if i.data['status'] == 'open':
            log.printerr("Ticket '%s' already open" % sha7)
            sys.exit(1)

        # Now, when the edit has succesfully taken place, switch branches, commit,
        # and switch back
        curr_branch = self.repo.active_branch.name
        curr_dir = os.getcwd()
        msg = "Ticket '%s' reopened" % sha7
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        try:
            os.chdir(self.repo.working_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            i.data['status'] = 'open'
            i.save()
            self.repo.git.commit(['-m', msg, match])
            print(msg)

        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
            os.chdir(curr_dir)


    def take_ticket(self, sha):
        i, _, fullsha, match = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)
        fullname = self.get_cfg('name', section='user', default='Anonymous')
        if i.data['assigned_to'] == fullname:
            print("Ticket '%s' already taken by '%s'" % (sha7, fullname))
            return

        msg = "Ticket '%s' taken by '%s'" % (sha7, fullname)
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        # prepare for critical section
        curr_branch = self.repo.active_branch.name
        curr_dir = os.getcwd()

        try:
            os.chdir(self.repo.working_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            i.data['assigned_to'] = fullname
            i.save()
            self.repo.git.commit(['-m', msg, '--', match])
            print(msg)
        except Exception:
            print("Error commiting change -- cleanup")
        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
            os.chdir(curr_dir)


    def leave_ticket(self, sha):
        i, _, fullsha, match = self.get_ticket(sha)
        sha7 = misc.chop(fullsha, 7)
        fullname = self.get_cfg('name', section='user', default='Anonymous')

        if i.data['assigned_to'] == '-':
            print("Ticket '%s' already left alone" % (sha7))
            return

        # prepare for the critical section
        curr_branch = self.repo.active_branch.name
        curr_dir = os.getcwd()
        msg = "Ticket %s was left alone from '%s'" % (sha7, fullname)
        abs_ticket_dir = os.path.join(self.repo.working_dir, it.TICKET_DIR)

        try:
            os.chdir(self.repo.working_dir)
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+it.ITDB_BRANCH])
            i.data['assigned_to'] = '-'
            i.save()
            self.repo.git.commit(['-m', msg, match])
            print(msg)
        except Exception:
            print("Error commiting change -- cleanup")
        finally:
            self.repo.git.symbolic_ref(['HEAD', 'refs/heads/'+curr_branch])
            self.repo.git.reset(['HEAD', '--', abs_ticket_dir])
            misc.rmdirs(abs_ticket_dir)
            os.chdir(curr_dir)

#EOF

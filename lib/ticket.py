#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

import os
import datetime
import colors
import math
import misc
import log
import it
from git import Repo

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class MissingTicketFieldException(Exception): pass
class MalformedTicketFieldException(Exception): pass

def parse_datetime_string(dt):
    dt = dt.strip()
    date, time = dt.split(' ')
    year, month, day = date.split('-', 2)
    hour, minute, second = time.split(':', 2)
    return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))

# Helper functions for asking interactive input
def not_empty(s):
    return s.strip() != ''

def is_int(s):
    try:
        int(s)
    except ValueError:
        return False
    return True

def ask_for_pattern(message, pattern = None, default=None):
    input = raw_input(message)
    if default and input == '':
        input = default
    if pattern:
        while not pattern(input):
            input = raw_input(message)
    return input


#
# Helper functions for creating new tickets interactively or from file
#
def create_interactive(git_cfg):
    # First, do some checks to error early
    try:
        fullname = git_cfg.get('user', 'name')
    except Exception as e:
        log.printerr("""
Author name not set. Use

    git config [--global] user.name "John Smith"

to set the fullname.
""")
        return
    try:
        email = git_cfg.get('user', 'email')
    except Exception as e:
        log.printerr("""
Email address not set. Use

        git config [--global] user.email "john@smith.org"

to set the email address.
""")
        return

    i = Ticket()
    i.title = ask_for_pattern('Title: ', not_empty)

    type_dict = { 'i': 'issue', 't': 'task', 'f': 'feature', 'b': 'bug' }
    type_string = ask_for_pattern(
            'Type [(b)ug, (f)eature, (i)ssue, (t)ask]: ',
            lambda x: not_empty(x) and x.strip() in 'bfit',
            default = 'i'
    )
    i.type = type_dict[type_string]

    prio_string = ask_for_pattern(
            'Priority [(1)high, (2)medium, (3)low]: ',
            lambda x: x.strip() in '123',
            default='2'
    )
    i.prio = int(prio_string)

    i.weight = int(ask_for_pattern(
        'Weight [1-27] (1=small, 3=minor, 9=major, 27=super): ',
        lambda x: is_int(x) and 1 <= int(x) <= 27,
        default='3'
    ))

    i.release = ask_for_pattern('Release: ', default=it.UNCATEGORIZED)

    #FIXME: add ticket description as body
    #i.body = ask_for_multiline_pattern('Describe the ticket:\n')

    i.status = 'open'
    i.date = datetime.datetime.now()
    i.issuer = '%s <%s>' % (fullname, email)
    return i

def create_from_lines(array_with_lines, id = None, release = None, backward_compatible = False):
    # Create an empty ticket
    i = Ticket()

    # Parse the lines
    ticket = {}
    ticket[None] = ''
    in_body = False
    for line in array_with_lines:
        # skip comment lines
        if line.startswith('#'):
            continue

        # when we're in the body, just append lines
        if in_body or line.strip() == '':
            in_body = True
            ticket[None] += line + os.linesep
            continue

        pos = line.find(':')
        if pos < 0:
            raise MalformedTicketFieldException, 'Cannot parse field "%s".' % line

        key = line[:pos].strip()
        val = line[pos+1:].strip()
        ticket[key] = val

    # Validate if all fields are present
    requires_fields_set = ['Subject', 'Type', 'Issuer', 'Date', 'Priority',
             'Status', 'Assigned to']
    if not backward_compatible:
        requires_fields_set.append('Weight')
    for required_field in requires_fields_set:
        if not ticket.has_key(required_field):
            raise MissingTicketFieldException, 'Ticket misses field "%s". Parsed so far: %s' % (required_field, ticket)

    # Now, set the ticket fields
    i.title = ticket['Subject']
    i.type = ticket['Type']
    i.issuer = ticket['Issuer']
    i.date = parse_datetime_string(ticket['Date'])
    i.body = ticket[None].strip()
    i.prio = int(ticket['Priority'])
    if ticket.has_key('Weight'):  # weight was added later, be backward compatible
        i.weight = int(ticket['Weight'])
    i.status = ticket['Status']
    i.assigned_to = ticket['Assigned to']

    # Properties that are not part of the content, but of the location of the file
    # These properties may be overwritten by the caller, else we will use defaults
    if id:
        i.id = id

    if i.release:
        i.release = release

    # Return the new ticket
    return i

def create_from_string(content, id = None, release = None, backward_compatible = False):
    lines = content.split(os.linesep)
    return create_from_lines(lines, id, release, backward_compatible)

def create_from_file(filename, overwrite_id = None, overwrite_release = None):
    if bool(overwrite_id) ^ bool(overwrite_release):
        raise Exception("specify alternative id AND alternative release OR neither")

    if overwrite_id:
        id = overwrite_id
    else:
        dir, id = os.path.split(filename)

    if overwrite_release:
        release = overwrite_release
    else:
        _, release = os.path.split(dir)

    content = misc.read_file_contents(filename)
    if not content:
        return None
    else:
        return create_from_string(content, id, release)


class Ticket:
    # Private fields
    prio_names = [ 'high', 'med', 'low' ]
    prio_colors = { 'high': 'red-on-white', 'med': 'yellow-on-white', 'low': 'white' }
    status_colors = { 'open': 'bold', \
                                        'test': 'bold', \
                                        'closed': 'default', \
                                        'rejected': 'red-on-white', \
                                        'fixed': 'green-on-white' }
    # weight n will be 3 times as large as weight n-1
    # so in order to get the real weight from the name:
    #   weight = 3 ** weight_names.index(name)
    # and to get the most appropriate name back from a number:
    #   approx_name = weight_names[min(3,max(0, int(round(math.log(weight, 3)))))]
    weight_names = [ 'small', 'minor', 'major', 'super' ]

    def __init__(self):
        self.title = ''
        self.type = 'issue'
        self.issuer = ''
        self.date = datetime.datetime.now()
        self.body = ''
        self.prio = 3
        self.id = '000000'
        self.status = 'open'
        self.assigned_to = '-'
        self.weight = 3  # the weight of 'minor' by default
        self.release = it.UNCATEGORIZED
        self.working_dir = Repo().working_dir

    def is_mine(self, fullname):
        return self.assigned_to == fullname

    def oneline(self, cols, annotate_ownership):
        colstrings = []
        for col in cols:
            if not col['visible']:
                continue

            w = col['width']
            id = col['id']
            if id == 'id':
                colstrings.append(misc.chop(self.id, w))
            elif id == 'type':
                colstrings.append(misc.pad_to_length(self.type, w))
            elif id == 'date':
                colstrings.append(misc.pad_to_length('%d-%02d-%02d'
                    % (self.date.year, self.date.month, self.date.day), w))
            elif id == 'title':
                title = self.title
                if self.assigned_to != '-' and annotate_ownership:
                    name_suffix = ' (%s)' % self.assigned_to.split()[0]
                    w = w - len(name_suffix)
                    title = '%s%s' % (misc.pad_to_length(misc.chop(title, w, '..'), w), name_suffix)
                else:
                    title = misc.pad_to_length(misc.chop(title, w, '..'), w)
                colstrings.append('%s%s%s' % (colors.colors[self.status_colors[self.status]],        \
                                                                            title, \
                                                                            colors.colors['default']))
            elif id == 'status':
                colstrings.append('%s%s%s' % (colors.colors[self.status_colors[self.status]],        \
                                                                            misc.pad_to_length(self.status, 8),                             \
                                        colors.colors['default']))
            elif id == 'prio':
                priostr = self.prio_names[self.prio-1]
                colstrings.append('%s%s%s' % (colors.colors[self.prio_colors[priostr]],              \
                                                                            misc.pad_to_length(priostr, 4),
                                        colors.colors['default']))
            elif id == 'wght':
                weightstr = self.weight_names[min(3, max(0, int(round(math.log(self.weight, 3)))))]
                colstrings.append(misc.pad_to_length(weightstr, 5))

        return ' '.join(colstrings)

    def __str__(self):
        headers = [ 'Subject: %s'     % self.title,
                                'Issuer: %s'      % self.issuer,
                                'Date: %s'        % self.date.strftime(DATE_FORMAT),
                                'Type: %s'        % self.type,
                                'Priority: %d'    % self.prio,
                                'Weight: %d'      % self.weight,
                                'Status: %s'      % self.status,
                                'Assigned to: %s' % self.assigned_to,
                                'Release: %s'     % self.release,
                                '',
                                self.body
                            ]
        return os.linesep.join(headers)

    def print_ticket_field(self, field, value, color_field = None, color_value = None):
        if not color_field:
            color_field = 'red-on-white'
        if not color_value:
            color_value = 'default'
        print("%s%s:%s %s%s%s" %
                (colors.colors[color_field], field, colors.colors['default'], \
                colors.colors[color_value], value, colors.colors['default'])
        )

    def print_ticket(self, fullsha = None):
        if fullsha:
            self.print_ticket_field('Ticket', fullsha)
        self.print_ticket_field('Subject', self.title)
        self.print_ticket_field('Issuer', self.issuer)
        self.print_ticket_field('Date', self.date)
        self.print_ticket_field('Type', self.type)
        self.print_ticket_field('Priority', self.prio)
        self.print_ticket_field('Weight', self.weight)
        self.print_ticket_field('Status', self.status, None, self.status_colors[self.status])
        self.print_ticket_field('Assigned to', self.assigned_to)
        self.print_ticket_field('Release', self.release)
        print('')
        print(self.body)

    def filename(self):
        file = os.path.join(self.working_dir, it.TICKET_DIR, self.release, self.id)
        return file

    def save(self, filename = None):
        headers = [ 'Subject: %s'     % self.title,
                                'Issuer: %s'      % self.issuer,
                                'Date: %s'        % self.date.strftime(DATE_FORMAT),
                                'Type: %s'        % self.type,
                                'Priority: %d'    % self.prio,
                                'Weight: %d'      % self.weight,
                                'Status: %s'      % self.status,
                                'Assigned to: %s' % self.assigned_to,
                                '',
                                self.body
                            ]
        contents = os.linesep.join(headers)

        # If an explicit file name is not given, calculate the default
        if filename is None:
            filename = self.filename()

        # Write the file
        dir, _ = os.path.split(filename)
        if dir and not os.path.isdir(dir):
            misc.mkdirs(dir)
        f = open(filename, 'w')
        try:
            f.write(contents)
        finally:
            f.close



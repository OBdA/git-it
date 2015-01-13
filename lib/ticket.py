#vim: syntax=python fileencoding=utf-8 tabstop=4 expandtab shiftwidth=4

import os
import datetime
import re

import math
import misc
import log
import it
from git import Repo


import hashlib
sha1_constructor = hashlib.sha1


DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


# and the allowed type. _requirement status_ may be 'req' (required)
# or 'opt' (optional). The _allowed type_ is a type, class or tuple.
# Third field is the printing order as int.
#TICKET_FIELDS = {  'id': ('opt',str,1), 'type': ('req',str,4), 'subject': ('req',str,2),
#            'priority': ('req',int,5), 'weight': ('opt',int,6),
#            'created': ('req',datetime.datetime,7),
#            'last_modified': ('opt', datetime.datetime,8),
#            'issuer': ('req',str,3), 'assigned_to': ('opt',str,9),  # person
#            'status': ('req',str,10),                      # status
#            'release': ('opt',str,11),                     # milestone
#            'body': ('opt',str,12),                        # content (incl. comments?)
#        }

# For compatibility to ticket format of it version prior 0.3 these fields
# must be optional:
# + created
# + id
# + last_modified
# + release
#
# The following fields must be configured as alias:
# + date -> created

# TICKET_FIELDS
# each ticket field is represented with hash entry which value is another
# hash, containing one or more of the following fields:
# + name (str)
# + alias (str)
# + required (bool)
# + type (class)
# + order (int)
#
TICKET_FIELDS = {
        'id':      {'name': 'id',      'required': False, 'type': str, 'order': 1},
        'issuer':  {'name': 'issuer',  'required': True,  'type': str, 'order': 2},
        'date':    {'name': 'date', 'alias': 'created'},
        'created': {'name': 'created', 'required': True,  'type': datetime.datetime, 'order': 3},
        'type':    {'name': 'type',    'required': True,  'type': str, 'order': 4},
        'subject': {'name': 'subject', 'required': True,  'type': str, 'order': 5},
        'priority':{'name': 'priority','required': True,  'type': int, 'order': 6},
        'weight':  {'name': 'weight',  'required': False, 'type': int, 'order': 7},
        'status':  {'name': 'status', 'required': True, 'type': str, 'order': 8},
        'assigned_to':{'name': 'assigned_to', 'required': False, 'type': str, 'order': 9},
        'release': {'name': 'release', 'required': False, 'type': str, 'order': 10},
        'last_modified': {'name': 'last_modified', 'required': False, 'type': datetime.datetime, 'order': 11},
        'body':    {'name': 'body',   'required': False, 'type': str, 'order': 12}
}

# TICKET_TYPES defines allowed strings for the type of the ticket
# (as keys) and get (as values) the string to use for this type.
TICKET_TYPES  = {
        'error': 'error', 'bug': 'error',
        'issue': 'issue',
        'feature': 'feature',
        'task': 'task'
        }

priorities = [ 'high', 'med', 'low' ]
weight_names = [ 'small', 'minor', 'major', 'super' ]
# weight n will be 3 times as large as weight n-1
# so in order to get the real weight from the name:
#   weight = 3 ** weight_names.index(name)
# and to get the most appropriate name back from a number:
#   approx_name = weight_names[min(3,max(0, int(round(math.log(weight, 3)))))]

# Colors
#prio_colors = {
#    'high': 'red-on-white',
#    'med':  'yellow-on-white',
#    'low':  'white'
#}
#status_colors = {
#    'open':     'bold',
#    'test':     'bold',
#    'closed':   'default',
#    'rejected': 'red-on-white',
#    'fixed':    'green-on-white'
#}



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
    # FIXME: FIXME before deletion!
    # FIXME: move check for author's name and email to git-it initialisation
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
    i.data['subject'] = ask_for_pattern('Title: ', not_empty)

    type_dict = { 'i': 'issue', 't': 'task', 'f': 'feature', 'b': 'bug' }
    type_string = ask_for_pattern(
            'Type [(b)ug, (f)eature, (i)ssue, (t)ask]: ',
            lambda x: not_empty(x) and x.strip() in 'bfit',
            default = 'i'
    )
    i.data['type'] = type_dict[type_string]

    prio_string = ask_for_pattern(
            'Priority [(1)high, (2)medium, (3)low]: ',
            lambda x: x.strip() in '123',
            default='2'
    )
    i.data['priority'] = int(prio_string)

    i.data['weight'] = int(ask_for_pattern(
        'Weight [1-27] (1=small, 3=minor, 9=major, 27=super): ',
        lambda x: is_int(x) and 1 <= int(x) <= 27,
        default='3'
    ))

    i.data['release'] = ask_for_pattern('Release: ', default=it.UNCATEGORIZED)

    #FIXME: add ticket description as body
    #i.data['body'] = ask_for_multiline_pattern('Describe the ticket:\n')

    i.data['status'] = 'open'
    i.data['created'] = datetime.datetime.now()
    i.data['issuer'] = '%s <%s>' % (fullname, email)
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
    i.data['subject'] = ticket['Subject']
    i.data['type'] = ticket['Type']
    i.data['issuer'] = ticket['Issuer']
    i.data['created'] = parse_datetime_string(ticket['Date'])
    i.data['body'] = ticket[None].strip()
    i.data['priority'] = int(ticket['Priority'])
    if ticket.has_key('Weight'):  # weight was added later, be backward compatible
        i.data['weight'] = int(ticket['Weight'])
    i.data['status'] = ticket['Status']
    i.data['assigned_to'] = ticket['Assigned to']

    # Properties that are not part of the content, but of the location of the file
    # These properties may be overwritten by the caller, else we will use defaults
    if id:
        i.data['id'] = id

    if i.data['release']:
        i.data['release'] = release

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


def parse_datetime(string):
    try:
        dt = datetime.datetime.strptime(string,'%Y-%m-%dT%H:%M:%S.%f')
    except ValueError:
        try:
            dt = datetime.datetime.strptime(string,'%Y-%m-%dT%H:%M:%S')
        except ValueError:
            try:
                dt = datetime.datetime.strptime(string,'%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                try:
                    dt = datetime.datetime.strptime(string,'%Y-%m-%d %H:%M:%S')
                except ValueError as ex:
                    raise RuntimeError('Can not determin date format', ex)
    return dt

class NewTicket:
    """
    Defines general ticket behaviours for all ticket flavours.

    """

    def __init__(self, data=None, ticket_id=None, release=None):
        self.working_dir = Repo().working_dir

        # set default values for the new ticket
        now = datetime.datetime.isoformat(datetime.datetime.now())
        self.data = {
                'id': None,
                'type': 'issue',
                'subject': None,
                'issuer': None,
                'created': now,
                # do not set a default for 'last_modified'
                'priority': 3,
                'status': 'open',
                'assigned_to': None,
                'weight': 3,
                'release': it.UNCATEGORIZED,
                'body': '',
        }

        if data is None:
            self.read_interactivly()

        elif isinstance(data, file):
            self.read_file(data)

        elif isinstance(data, (list, tuple)):
            self._from_lines(data)

        elif isinstance(data, dict):
            # overwrite defaults
            for key in data:
                if key in TICKET_FIELDS:
                    self.data[key] = data[key]
                else:
                    log.printerr("Ignore unknown ticket field '%s'" % key)

        # FIXME: check all fields (requirement and type)

        # FIXME: check the 'type' field

        if self.data['id'] is None:
            if ticket_id is None:
                # create uniq SHA1 ID
                s = sha1_constructor()
                s.update(str(self))
                #s.update(os.getlogin())
                #s.update(datetime.datetime.now().__str__())
                self.data['id'] = s.hexdigest()
            else:
                # compatibility git-it <= 0.2
                self.data['id'] = ticket_id

        # compatibility git-it <= 0.2
        if self.data['release'] is it.UNCATEGORIZED and release is not None:
            self.data['release'] = release

        return


    @property
    def id(self):
        return self.data['id']

    @property
    def release(self):
        return self.data['release']

    def __str__(self):
        return """Id: {id}\nSubject: {subject}\nIssuer: {issuer}
Created: {created}\nLast modified: {last_modified}\nType: {type}
Priority: {priority}\nWeight: {weight}
Status: {status}\nAssigned to: {assigned_to}\nRelease: {release}

{body}""".format(**self.data)


    def get_field(self, field, default=None):
        """ Get value of _field_. Return _default_ (default: None) if
            field is not set.
        """
        assert field in TICKET_FIELDS.keys(), "Unknown ticket field '%s'" % field

        if self.data[field] is not None:
            return self.data[field]

        return default


    def set_field(self, field, value):
        """ Set tickets _field_ to _value_ and return the old value.
            Return None if nothing has changed.
        """
        assert field in TICKET_FIELDS.keys(), "Unknown ticket field '%s'" % field

        if self.data[field] != value:
            oldval = self.get_field(field)
            self.data[field] = value
            return oldval
        else:
            return None

    def set_default(self, field, value):
        assert field in TICKET_FIELDS.keys(), "Unknown ticket field '%s'" % field

        if self.data[field] is None:
            self.data[field] = value


    def read_interactivly(self):
        import readline

        # get title
        self.data['subject'] = ask_for_pattern('Title: ', not_empty)

        # get type of issue
        #FIXME: set the readline completion to allowed the ticket types
        #type_dict = { 'i': 'issue', 't': 'task', 'f': 'feature', 'b': 'bug' }
        self.data['type'] = ask_for_pattern(
                    'Type [issue (default), error, feature, task]: ',
                    lambda x: not_empty(x) and x.strip() in TICKET_TYPES.values(),
                    default = 'issue'
        )

        # form a stringwith all priorities like '(num)prio' -- comma separated
        text = 'Priority [%s]' % ', '.join(
                ['(%d)%s' % (i+1, priorities[i])
                    for i in range(0,len(priorities))])
        prio_string = ask_for_pattern(
                text,
                lambda x: x.strip() in ''.join(map(str, range(1, len(priorities)+1))),
                default='2'
        )
        self.data['priority'] = int(prio_string)

        # get weight
        self.data['weight'] = int(ask_for_pattern(
                'Weight [1-27] (1=small, 3=minor, 9=major, 27=super): ',
                lambda x: is_int(x) and 1 <= int(x) <= 27,
                default='3'
        ))

        # get release (or milestone)
        #Feature: get all available releases and configure a readline completer
        self.data['release'] = ask_for_pattern('Release: ', default=it.UNCATEGORIZED)

        #FIXME: add ticket description as body
        #self.data['body'] = ask_for_multiline_pattern('Describe the ticket:\n')

        self.update_last_modified()
        return

    def update_last_modified(self):
        self.data['last_modified'] = datetime.datetime.isoformat(datetime.datetime.now())

    def read_file(self, fd):
        self._from_lines(fd.readlines())

    def _from_lines(self, lines):
        # Parse the lines
        ticket = {}
        ticket['body'] = ''
        in_body = False
        for line in lines:
            line = line.strip()
            if not in_body and line == '':
                in_body = True
                continue

            # when we're in the body, just append lines
            elif in_body:
                ticket['body'] += line + os.linesep
                continue

            if line.find(':') < 0:
                raise MalformedTicketFieldException, 'Cannot parse field "%s".' % line
            key,val = line.split(':', 1)
            # take lower case and replace any 'whitespace' to '_' in key
            key = re.sub('\s', '_', key.lower())
            val = val.strip()

            # calculate aliases
            if key in TICKET_FIELDS and 'alias' in TICKET_FIELDS[key]:
                key = TICKET_FIELDS[key]['alias']
            ticket[key] = val

        for field in TICKET_FIELDS:
            if field in ticket:
                # set the ticket field depending on type
                if str == TICKET_FIELDS[field]['type']:
                    self.data[field] = ticket[field]
                elif int == TICKET_FIELDS[field]['type']:
                    self.data[field] = int(ticket[field])
                elif datetime.datetime == TICKET_FIELDS[field]['type']:
                    self.data[field] = parse_datetime(ticket[field])
            else:
                if TICKET_FIELDS[field].get('required'):
                    raise MissingTicketFieldException("Missing field '%s'" % field)

        return


    def save(self, filename = None):

        # If an explicit file name is not given, calculate the default
        if filename is None:
            filename = self.filename

        # Write the file
        dir, _ = os.path.split(filename)
        if dir and not os.path.isdir(dir):
            misc.mkdirs(dir)
        with open(filename, 'w') as fd:
            fd.write(str(self))

        return


    @property
    def filename(self):
            return os.path.join(
                    self.working_dir, it.TICKET_DIR,
                    self.data['release'], self.data['id'])

    def is_assigned_to(self, fullname):
        return self.data['assigned_to'] == fullname


    def cmp_by(self, other, what='created'):
        assert what in TICKET_FIELDS, "Ticket has no field '%s'" % what
        return cmp(self.data[what], other.data[what])


    def oneline(self, cols, annotate_ownership):
        colstrings = []
        for col in cols:
            if not col['visible']:
                continue

            w = col['width']
            id = col['id']
            if id == 'id':
                colstrings.append(misc.chop(self.data['id'], w))
            elif id == 'type':
                colstrings.append(misc.pad_to_length(self.data['type'], w))
            elif id == 'date':
                colstrings.append(misc.pad_to_length('%d-%02d-%02d'
                    % ( self.data['created'].year,
                        self.data['created'].month,
                        self.data['created'].day), w))
            elif id == 'title':
                title = self.data['subject']
                if self.data['assigned_to'] != '-' and annotate_ownership:
                    name_suffix = ' (%s)' % self.data['assigned_to'].split()[0]
                    w = w - len(name_suffix)
                    title = '%s%s' % (misc.pad_to_length(
                        misc.chop(title, w, '..'), w),
                        name_suffix)
                else:
                    title = misc.pad_to_length(misc.chop(title, w, '..'), w)
                # colored: <title-color> title <default>
                colstrings.append(title)
            elif id == 'status':
                # colored: <status-color> status:8 <default>
                colstrings.append(misc.pad_to_length(self.data['status'], 8))
            elif id == 'prio':
                priostr = priorities[self.data['priority'] -1]
                # colored: <prio-color> prio:4 <default>
                colstrings.append(misc.pad_to_length(priostr, 4))
            elif id == 'wght':
                weightstr = weight_names[min(3,
                    max(0, int(round(math.log(self.data['weight'], 3)))))]
                colstrings.append(misc.pad_to_length(weightstr, 5))

        return ' '.join(colstrings)

    def print_ticket(self):
        #print(self)

        # sort the ticket fields with the 'order' field
        fields = [(k,v) for k,v in TICKET_FIELDS.items()
                if 'alias' not in v and k != 'body']
        fields.sort(key=lambda x: x[1]['order'])

        for field in fields:
            # skip all values not defined for this ticket
            k,v = field
            if k not in self.data: continue
            key = v['visual'] if 'visual' in field else v['name'].capitalize()
            value = self.data[k]
            # colored: <red-on-white> key <default> <default> value <default>
            print("%s: %s" % (key, value))
        body = '' if self.data['body'] is None else self.data['body']
        print("\n%s" % body)

#EOF

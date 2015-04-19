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
                'assigned_to': '-',
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

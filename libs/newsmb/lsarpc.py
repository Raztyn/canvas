#!/usr/bin/env python
##ImmunityHeader v1
################################################################################
## File       :  lsarpc.py
## Description:
##            :
## Created_On :  Tue Dec 20 2014
## Created_By :  X.
##
## (c) Copyright 2010, Immunity, Inc. all rights reserved.
################################################################################

# The API is not 100% written but is currently working quite well.

import sys
import logging
from struct import pack, unpack

if '.' not in sys.path:
    sys.path.append('.')

from libs.newsmb.libdcerpc import DCERPC, DCERPCString, DCERPCSid
from libs.newsmb.libdcerpc import RPC_C_AUTHN_WINNT, RPC_C_AUTHN_LEVEL_PKT_INTEGRITY
from libs.newsmb.Struct import Struct

###
# Constants
###

# The RPC methods

LSA_COM_OPEN_POLICY2 = 44
LSA_COM_LOOKUP_NAMES = 14
LSA_COM_LOOKUP_NAMES3 = 68
LSA_COM_LOOKUP_SIDS = 15
LSA_COM_GET_USER_NAME = 45
LSA_COM_CLOSE = 0

# typedef  enum _SID_NAME_USE

SIDTYPEUSER = 1
SIDTYPEGROUP = 2
SIDTYPEDOMAIN = 3
SIDTYPEALIAS = 4
SIDTYPEWELLKNOWNGROUP = 5
SIDTYPEDELETEDACCOUNT = 6
SIDTYPEINVALID = 7
SIDTYPEUNKNOWN = 8
SIDTYPECOMPUTER = 9
SIDTYPELABEL = 10

# ACCESS_MASK

GENERIC_READ           = 0x80000000
GENERIC_WRITE          = 0x40000000
GENERIC_EXECUTE        = 0x20000000
GENERIC_ALL            = 0x10000000
MAXIMUM_ALLOWED        = 0x02000000
ACCESS_SYSTEM_SECURITY = 0x01000000

STANDARD_SYNCHRONISE   = 0x00100000
STANDARD_WRITE_OWNER   = 0x00080000
STANDARD_WRITE_DAC     = 0x00040000
STANDARD_READ_CONTROL  = 0x00020000
STANDARD_DELETE        = 0x00010000

LSA_POLICY_NOTIFICATION = 4096
LSA_POLICY_LOOKUP_NAMES = 2048
LSA_POLICY_SERVER_ADMIN = 1024
LSA_POLICY_AUDIT_LOG_ADMIN = 512
LSA_POLICY_SET_AUDIT_REQUIREMENTS = 256
LSA_POLICY_SET_DEFAULT_QUOTA_LIMITS = 128
LSA_POLICY_CREATE_PRIVILEGE = 64
LSA_POLICY_CREATE_SECRET = 32
LSA_POLICY_CREATE_ACCOUNT = 16
LSA_POLICY_TRUST_ADMIN = 8
LSA_POLICY_GET_PRIVATE_INFORMATION = 4
LSA_POLICY_VIEW_AUDIT_INFORMATION = 2
LSA_POLICY_VIEW_LOCAL_INFORMATION = 1

# LSA Lookup levels

LSA_LOOKUP_NAMES_ALL = 1
LSA_LOOKUP_NAMES_DOMAINS_ONLY = 2
LSA_LOOKUP_NAMES_PRIMARY_DOMAIN_ONLY = 3
LSA_LOOKUP_NAMES_UPLEVEL_TRUSTS_ONLY = 4,
LSA_LOOKUP_NAMES_FOREST_TRUSTS_ONLY = 5
LSA_LOOKUP_NAMES_UPLEVEL_TRUSTS_ONLY2 = 6


###
# LSA Objects.
# No exception handling for these objects.
###


class LsaPolicyHandle(Struct):
    st = [
        ['Handle', '16s', '\x00'*16],
    ]

    def __init__(self, data=None, Handle=''):

        if data is not None:
            Struct.__init__(self, data)
        else:
            self['Handle'] = Handle

    def pack(self):
        return Struct.pack(self)

class LsaObjectAttributes(Struct):
    st = [
        ['Len', '<L', 0],                      # ignored
        ['RootDirectory', '<L', 0],            # ignored
        ['ObjectName', '<L', 0],               # ignored
        ['Attributes', '<L', 0],
        ['SecurityDescriptor', '<L', 0],       # ignored
        ['SecurityQualityOfService', '<L', 0], # ignored
    ]

    def __init__(self, data=None, Attributes=0):
        Struct.__init__(self, data)

        if not data:
            self['Len'] = self.calcsize()
            self['Attributes'] = Attributes

    def pack(self):

        data = Struct.pack(self)
        return data


class LsaTrustInformation(Struct):
    st = [
        ['NameLength', '<H', 0 ],
        ['NameSize', '<H', 0 ],
        ['NamePtr', '<L', 0 ],
        ['SidPtr', '<L', 0 ],
        ['NameString', '0s', '' ],
        ['Sid', '0s', 0 ],
    ]

    def __init__(self, data=None, Name='', Sid=''):
        Struct.__init__(self, data)

        if data is None:
            if Name is not None:
                self['NameLength'] = len(Name)
                self['NameSize'] = len(Name)
                self['NamePtr'] = 0x2000040
                self['NameString'] = DCERPCString(string=Name.encode('UTF-16LE'))
            if Sid is not None:
                self['SidPtr'] = 0x2000050
                self['Sid'] = DCERPCSid(Sid=Sid)

    def has_name(self):
        return self['NamePtr'] != 0

    def has_sid(self):
        return self['SidPtr'] != 0

    def unpack_name(self, data):
        self['NameString'] = DCERPCString(data=data)

    def unpack_sid(self, data):
        self['Sid'] = DCERPCSid(data=data)

    def pack_name(self):
        return self['NameString'].pack(force_null_byte=0)

    def pack_sid(self):
        return self['Sid'].pack()

    def pack(self):
        data = Struct.pack(self)
        return data

    def get_domain(self):
        return {'Name':self['NameString'].get_string().decode('UTF-16LE'),
                'Sid':self['Sid'].get_sid() }


class LsaTranslatedSid(Struct):
    st = [
        ['SidType', '<H', 0 ],
        ['Padding', '<H', 0 ],
        ['Rid', '<L', 0 ],
        ['SidIndex', '<L', 0 ],
    ]

    def __init__(self, data=None, Rid=500):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)
        else:
            self['Rid'] = Rid

    def pack(self, pack_header=1, pack_string=0):

        data = Struct.pack(self)
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_rid(self):
        return { 'Type': self['SidType'], 'Rid':self['Rid'] }


class LsaTransSidArray(Struct):
    st = [
        ['Count', '<L', 0 ],
        ['SidsPtr', '<L', 0 ],
        ['MaxCount', '<L', 0 ],
        ['Sids', '0s', '' ]
    ]

    def __init__(self, data=None, Sids=[]):
        Struct.__init__(self, data)

        if data is not None:
            pos = self.calcsize()
            objsize = LsaTranslatedSidEx2().calcsize()
            self['Sids'] = []

            for i in xrange(self['Count']):
                Sid = LsaTranslatedSid(data=data[pos:])
                self['Sids'].append(Sid)
                pos += Sid.calcsize()

        else:
            self['Count'] = len(Sids)
            self['SidsPtr'] = 0x020010
            self['MaxCount'] = len(Sids)
            self['Sids'] = Sids

    def pack(self):

        if not self['Count']:
            data = pack('<LL', 0, 0)
        else:
            data = Struct.pack(self)
            for sid in self['Sids']:
                data += sid.pack()
            #for sid in self['Sids']:
            #    data += sid.pack(pack_header=0, pack_string=1)
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_rids(self):
        rids = [ sid.get_rid() for sid in self['Sids'] ]
        return rids

    def get_number_of_rids(self):
        return self['Count']


class LsaTranslatedSidEx2(Struct):
    st = [
        ['SidType', '<H', 0 ],
        ['Padding', '<H', 0 ],
        ['SidPtr', '<L', 0 ],
        ['DomainIndex', '<L', 0 ],
        ['Flags', '<L', 0 ],
        ['Sid', '0s', '' ]
    ]

    def __init__(self, data=None, extradata=None):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)
            pos = self.calcsize()
            self['Sid'] = DCERPCSid(data=extradata)

    def pack(self, pack_header=1, pack_string=0):

        data = ''
        if pack_header:
            data += Struct.pack(self)
        if pack_string:
            data += self['Sid'].pack()
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_sid(self):
        return { 'Type': self['SidType'], 'Sid':self['Sid'].get_sid() }

class LsaTransSidArrayEx2(Struct):
    st = [
        ['Count', '<L', 0 ],
        ['SidsPtr', '<L', 0 ],
        ['MaxCount', '<L', 0 ],
        ['Sids', '0s', '' ]
    ]

    def __init__(self, data=None, Sids=[]):
        Struct.__init__(self, data)

        if data is not None:
            pos1 = self.calcsize()
            objsize = LsaTranslatedSidEx2().calcsize()
            pos2 = pos1+objsize*self['Count']
            self['Sids'] = []
            for i in xrange(self['Count']):
                Sid = LsaTranslatedSidEx2(data=data[pos1:], extradata=data[pos2:])
                self['Sids'].append(Sid)
                pos1 += Sid.calcsize()
                sid_str = Sid.get_sid()['Sid']
                pos2 += len(DCERPCSid(Sid=sid_str).pack())
        else:
            self['Count'] = len(Sids)
            self['SidsPtr'] = 0x020010
            self['MaxCount'] = len(Sids)
            self['Sids'] = Sids

    def pack(self):

        if not self['Count']:
            data = pack('<LL', 0, 0)
        else:
            data = Struct.pack(self)
            for sid in self['Sids']:
                data += sid.pack(pack_header=1, pack_string=0)
            for sid in self['Sids']:
                data += sid.pack(pack_header=0, pack_string=1)
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_sids(self):
        sids = [ sid.get_sid() for sid in self['Sids'] ]
        return sids


class LsaTranslatedNameEx2(Struct):
    st = [
        ['SidType', '<H', 0 ],
        ['Padding', '<H', 0 ],
        ['Length', '<H', 0 ],
        ['Size', '<H', 0 ],
        ['StringPtr', '<L', 0 ],
        ['SidIndex', '<L', 0 ],
        ['Name', '0s', '' ]
    ]

    def __init__(self, data=None, extradata=None):
        Struct.__init__(self, data)

        if data is not None:
            pos = self.calcsize()
            if self['Length'] == 0:
                self['Name'] = DCERPCString(string='')
            else:
                self['Name'] = DCERPCString(data=extradata)

    def pack(self, pack_header=1, pack_string=0, force_null_byte=1):

        data = ''
        if pack_header:
            data += Struct.pack(self)
        if pack_string:
            data += self['Name'].pack(force_null_byte=force_null_byte)
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_name(self):
        name = self['Name'].get_string()
        return { 'Type': self['SidType'], 'Name': name }

class LsaTransNameArray(Struct):
    st = [
        ['Count', '<L', 0 ],
        ['NamesPtr', '<L', 0 ],
        ['MaxCount', '<L', 0 ],
        ['Names', '0s', '' ]
    ]

    def __init__(self, data=None, Sids=[]):
        Struct.__init__(self, data)

        if data is not None:
            pos1 = self.calcsize()
            objsize = LsaTranslatedNameEx2().calcsize()
            pos2 = pos1+objsize*self['Count']
            self['Names'] = []
            for i in xrange(self['Count']):
                Name = LsaTranslatedNameEx2(data=data[pos1:], extradata=data[pos2:])
                self['Names'].append(Name)
                pos1 += Name.calcsize()
                name_str = Name.get_name()['Name']
                if len(name_str):
                    pos2 += len(DCERPCString(string=name_str, is_unicode=False).pack())
        else:
            self['Count'] = len(Sids)
            self['NamesPtr'] = 0x020010
            self['MaxCount'] = len(Sids)
            self['Sids'] = Sids

    def pack(self):

        if not self['Count']:
            data = pack('<LL', 0, 0)
        else:
            data = Struct.pack(self)
            for name in self['Names']:
                data += name.pack(pack_header=1, pack_string=0)
            for name in self['Names']:
                if (name.get_name()['Name']):
                    data += name.pack(pack_header=0, pack_string=1, force_null_byte=0)
        #if (len(data) % 4) != 0:
        #    data += '\0' * (4 - (len(data) % 4))
        return data

    def get_names(self):
        names = [ name.get_name() for name in self['Names'] ]
        return names


class LsaReferencedDomainList(Struct):
    st = [
        ['Count', '<L', 0 ],
        ['DomainPtr', '<L', 0 ],
        ['MaxSize', '<L', 0 ],
        ['MaxCount', '<L', 0 ],
        ['Domains', '0s', '' ]
    ]

    def __init__(self, data=None, Domains=[]):
        Struct.__init__(self, data)

        if data is not None:
            self['Domains'] = []
            pos = self.calcsize()
            for i in xrange(self['Count']):
                 domain = LsaTrustInformation(data=data[pos:])
                 self['Domains'] += [domain]

            # If Count != 0 we have an array at DomainPtr
            if self['Count']:
                pos += self['Count'] * self['Domains'][0].calcsize()

            for i in xrange(len(self['Domains'])):
                domain = self['Domains'][i]
                if domain.has_name():
                    domain.unpack_name(data[pos:])
                    pos += len(domain.pack_name())
                if domain.has_sid():
                    domain.unpack_sid(data[pos:])
                    pos += len(domain.pack_sid())
        else:
            self['Count'] = len(Domains)
            self['MaxCount'] = len(Domains)
            self['Domains'] = []
            if self['Count']:
                self['DomainPtr'] = 0x20004
            self['MaxSize'] = 2048 # Useless field
            for domain in Domains:
                self['Domains'] += [ LsaTrustInformation(Name=domain['Name'], Sid=domain['Sid']) ]

    def pack(self):

        data = Struct.pack(self)
        if self['Domains']:
            # First we pack the header
            for domain in self['Domains']:
                data += domain.pack()
            # Then we pack the Name & Sid
            for domain in self['Domains']:
                if domain.has_name():
                    data += domain.pack_name()
                if domain.has_sid():
                    data += domain.pack_sid()
        # Then we need to pad
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        return data

    def get_domains(self):
        if not self['Domains']:
            return []
        else:
            return [ dom.get_domain() for dom in self['Domains'] ]

###
# Handlers
# No exception handling for these objects.
###

# Opnum 44
class LSAOpenPolicy2Request(Struct):
    st = [
        ['SystemName', '0s', ''],
        ['ObjectAttributes', '0s', ''],
        ['DesiredAccess' , '<L', 0]
    ]

    def __init__(self, data=None, SystemName='', ObjectAttributes=None, DesiredAccess=0, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)
            ### TODO
        else:
            self['SystemName'] = SystemName.encode('UTF-16LE')
            self['ObjectAttributes'] = ObjectAttributes
            self['DesiredAccess'] = DesiredAccess

            if not ObjectAttributes:
                self['ObjectAttributes'] = LsaObjectAttributes().pack()

    def pack(self):

        data = pack('<L', 0x20004)
        data += DCERPCString(string = self['SystemName']).pack()
        data += self['ObjectAttributes']
        data += Struct.pack(self)
        return data

class LSAOpenPolicy2Response(Struct):
    st = [
        ['PolicyHandle', '20s', '\x00'*20],
        ['retvalue', '<L', 0 ]
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, retvalue=0, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)
        else:
            self['PolicyHandle'] = PolicyHandle
            self['retvalue'] = retvalue

    def pack(self):
        return Struct.pack(self)

    def get_return_value(self):
        return self['retvalue']

    def get_handle(self):
        return self['PolicyHandle']

# Opnum 68
class LSALookupNames3Request(Struct):
    st = [
        ['PolicyHandle', '0s', ''],
        ['Count', '<L', 0],
        ['NamesArray', '0s', ''],
        ['SidArray', '0s', ''],
        ['LsaLookupLevel', '<H', 0],
        ['Padding', '<H', 0],
        ['Count2', '<L', 0],
        ['LookupOptions', '<L', 0],
        ['ClientRevision', '<L', 0]
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, NamesArray=[], LsaLookupLevel=LSA_LOOKUP_NAMES_ALL, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            self['PolicyHandle'] = data[:16]
            ### TODO
        else:
            self['PolicyHandle'] = PolicyHandle
            self['Count'] = len(NamesArray)
            self['NamesArray'] = [ name.encode('UTF-16LE') for name in NamesArray ]
            self['SidArray'] = []
            self['LsaLookupLevel'] = LsaLookupLevel
            self['Count2'] = 0

    def pack(self):

        # PolicyHandle
        data = self['PolicyHandle']
        # NamesArray
        names = self['NamesArray']
        data += pack('<L', self['Count'])
        data += pack('<L', self['Count'])
        size = 0
        for i in xrange(len(names)):
            size = len(names[i])
            data += pack('<H', size)
            data += pack('<H', size)
            data += pack('<L', 2+i)
        for i in xrange(len(names)):
            data += DCERPCString(string = names[i], is_unicode=True).pack(force_null_byte=0)
        # Padding is mandatory
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        # SidsArray
        data += LsaTransSidArrayEx2().pack()
        # Level
        data += pack('<H', self['LsaLookupLevel'])
        data += pack('<H', 0) # padding
        # Count
        data += pack('<L', 0)
        # Flags
        data += pack('<L', 0)
        data += pack('<L', 0)
        return data

class LSALookupNames3Response(Struct):
    st = [
        ['DomainsPtr', '<L', 0],
        ['Domains', '0s', ''],
        ['Sids', '0s', ''],
        ['Count', '<L', 0],
        ['retvalue', '<L', 0 ]
    ]

    def __init__(self, data=None, Domains=[], Sids=[], is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['DomainsPtr'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['Domains'] = LsaReferencedDomainList(data=data[pos:])
            pos += len(self['Domains'].pack())
            SidsObj = LsaTransSidArrayEx2(data=data[pos:])
            self['Sids'] = SidsObj
            pos += len(SidsObj.pack())
            self['Count'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['retvalue'] = unpack('<L', data[pos:pos+4])[0]
        else:
            self['DomainsPtr'] = 0x20004
            self['Domains'] = LsaReferencedDomainList(Domains=Domains)
            self['Sids'] = LsaTransSidArrayEx2(Sids=Sids)
            self['Count'] = len(Sids)
            self['retvalue'] = 0

    def pack(self):

        data = pack('<L', self['DomainsPtr'])
        if self['DomainsPtr']:
            data += self['Domains'].pack()
        data += self['Sids'].pack()
        data += pack('<L', self['Count'])
        data += pack('<L', self['retvalue'])
        return data

    def get_sids(self):
        return self['Sids'].get_sids()

    def get_domains(self):
        return self['Domains'].get_domains()

# Opnum 15
class LSALookupSidsRequest(Struct):
    st = [
        ['PolicyHandle', '0s', ''],
        ['NumberOfSids', '<L', 0],
        ['Sids', '0s', ''],
        ['NamesCount', '<L', 0],
        ['NamesPtr', '<L', 0],
        ['NamesArray', '0s', ''],
        ['LsaLookupLevel', '<H', 0],
        ['Padding', '<H', 0],
        ['Count', '<L', 0]
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, Sids=[], LsaLookupLevel=LSA_LOOKUP_NAMES_ALL, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            self['PolicyHandle'] = data[:16]
            ### TODO
        else:
            self['PolicyHandle'] = PolicyHandle
            self['NumberOfSids'] = len(Sids)
            self['Sids'] = [ DCERPCSid(Sid=x) for x in Sids ]
            self['LsaLookupLevel'] = LsaLookupLevel
            self['Count'] = len(Sids)

    def pack(self):

        # PolicyHandle
        data = self['PolicyHandle']
        # SidsArray
        data += pack('<L', self['NumberOfSids'])
        if self['NumberOfSids']:
            data += pack('<L', 0x200010)
            data += pack('<L', self['NumberOfSids'])
            for i in xrange(self['NumberOfSids']):
                data += pack('<L', 0x200020+0x10*i)
            for i in xrange(self['NumberOfSids']):
                data += self['Sids'][i].pack()
        else:
            data += pack('<L', 0)
        # NamesArray
        data += pack('<L', self['NamesCount'])
        data += pack('<L', self['NamesPtr'])
        if self['NamesCount']:
            self['NamesArray'].pack()
        # Padding is mandatory
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        # Level
        data += pack('<H', self['LsaLookupLevel'])
        data += pack('<H', self['Padding'])
        # Count
        data += pack('<L', self['Count'])
        return data

class LSALookupSidsResponse(Struct):
    st = [
        ['DomainsPtr', '<L', 0],
        ['Domains', '0s', ''],
        ['Names', '0s', ''],
        ['Count', '<L', 0],
        ['retvalue', '<L', 0 ]
    ]

    def __init__(self, data=None, Domains=[], Names=[], is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['DomainsPtr'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['Domains'] = LsaReferencedDomainList(data=data[pos:])
            pos += len(self['Domains'].pack())
            NamesObj = LsaTransNameArray(data=data[pos:])
            self['Names'] = NamesObj
            pos += len(NamesObj.pack())
            self['Count'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['retvalue'] = unpack('<L', data[pos:pos+4])[0]
        else:
            if Domains:
                self['DomainsPtr'] = 0x20004
                self['Domains'] = LsaReferencedDomainList(Domains=Domains)
            if Names:
                self['Count'] = len(Names)
                self['Names'] = LsaTransNameArray(Names=Names)
            self['retvalue'] = 0

    def pack(self):

        data = pack('<L', self['DomainsPtr'])
        if self['DomainsPtr']:
            data += self['Domains'].pack()
        data += self['Names'].pack()
        data += pack('<L', self['Count'])
        data += pack('<L', self['retvalue'])
        return data

    def get_names(self):
        return self['Names'].get_names()

    def get_domains(self):
        return self['Domains'].get_domains()

    # debugging routine
    def get_number_of_names(self):
        return self['Count']

# Opnum 0
class LSACloseRequest(Struct):
    st = [
        ['PolicyHandle', '20s', '\x00'*20]
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)
        else:
            self['PolicyHandle'] = PolicyHandle

    def pack(self):
        return Struct.pack(self)

class LSACloseResponse(Struct):
    st = [
        ['PolicyHandle', '20s', '\x00'*20],
        ['retvalue', '<L', 0 ]
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, retvalue=0, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            Struct.__init__(self, data)

        else:
            self['PolicyHandle'] = PolicyHandle

    def pack(self):
        return Struct.pack(self)

    def get_return_value(self):
        return self['retvalue']

# Opnum 45
class LSAGetUserNameRequest(Struct):
    st = [
        ['SystemNamePtr', '<L', 0],
        ['UserNamePtr', '<L', 0],
        ['DomainNamePtr', '<L', 0],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

    def pack(self):
        return Struct.pack(self)

# Opnum 14
class LSALookupNamesRequest(Struct):
    st = [
        ['PolicyHandle', '0s', ''],
        ['Count', '<L', 0],
        ['NamesArray', '0s', ''],
        ['SidArray', '0s', ''],
        ['LsaLookupLevel', '<H', 0],
        ['Padding', '<H', 0],
        ['Count2', '<L', 0],
    ]

    def __init__(self, data=None, PolicyHandle='\x00'*20, NamesArray=[], LsaLookupLevel=LSA_LOOKUP_NAMES_ALL, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            self['PolicyHandle'] = data[:16]
            ### TODO
        else:
            self['PolicyHandle'] = PolicyHandle
            self['Count'] = len(NamesArray)
            self['NamesArray'] = [ name.encode('UTF-16LE') for name in NamesArray ]
            self['SidArray'] = []
            self['LsaLookupLevel'] = LsaLookupLevel
            self['Count2'] = 0

    def pack(self):

        # PolicyHandle
        data = self['PolicyHandle']
        # NamesArray
        names = self['NamesArray']
        data += pack('<L', self['Count'])
        data += pack('<L', self['Count'])
        size = 0
        for i in xrange(len(names)):
            size = len(names[i])
            data += pack('<H', size)
            data += pack('<H', size)
            data += pack('<L', 2+i)
        for i in xrange(len(names)):
            data += DCERPCString(string = names[i], is_unicode=True).pack(force_null_byte=0)
        # Padding is mandatory
        if (len(data) % 4) != 0:
            data += '\0' * (4 - (len(data) % 4))
        # SidsArray
        data += LsaTransSidArray().pack()
        # Level
        data += pack('<H', self['LsaLookupLevel'])
        data += pack('<H', 0) # padding
        # Count
        data += pack('<L', 0)
        return data

class LSALookupNamesResponse(Struct):
    st = [
        ['DomainsPtr', '<L', 0],
        ['Domains', '0s', ''],
        ['Sids', '0s', ''],
        ['Count', '<L', 0],
        ['retvalue', '<L', 0 ]
    ]

    def __init__(self, data=None, Domains=[], Sids=[], is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['DomainsPtr'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['Domains'] = LsaReferencedDomainList(data=data[pos:])
            pos += len(self['Domains'].pack())
            SidsObj = LsaTransSidArray(data=data[pos:])
            self['Sids'] = SidsObj
            pos += len(SidsObj.pack())
            self['Count'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['retvalue'] = unpack('<L', data[pos:pos+4])[0]
        else:
            self['DomainsPtr'] = 0x20004
            self['Domains'] = LsaReferencedDomainList(Domains=Domains)
            self['Sids'] = LsaTransSidArray(Sids=Sids)
            self['Count'] = len(Sids)
            self['retvalue'] = 0

    def pack(self):

        data = pack('<L', self['DomainsPtr'])
        if self['DomainsPtr']:
            data += self['Domains'].pack()
        data += self['Sids'].pack()
        data += pack('<L', self['Count'])
        data += pack('<L', self['retvalue'])
        return data

    def get_rids(self):
        return self['Sids'].get_rids()

    def get_sids(self):
        doms = self['Domains'].get_domains()
        rids = self['Sids'].get_rids()
        sids = []
        dom_sid = doms[0]['Sid']
        for rid in rids:
            sids.append({'Sid':'-'.join([dom_sid,str(rid['Rid'])]), 'Type':rid['Type']})
        return sids

    def get_domains(self):
        return self['Domains'].get_domains()

#######################################################################
#####
##### Exception classes
#####
#######################################################################

class LSAException(Exception):
    """
    Base class for all LSA-specific exceptions.
    """
    def __init__(self, message=''):
        self.message = message

    def __str__(self):
        return '[ LSA_ERROR: %s ]' % (self.message)

class LSAException2(Exception):
    """
    Improved version of the base class to track errors.
    """
    def __init__(self, message='', status=None):
        self.message = message
        self.status = status

    def __str__(self):
        if not self.status:
            return '[ LSA_ERROR: %s ]' % (self.message)
        else:
            return '[ LSA_ERROR: %s (0x%x) ]' % (self.message, self.status)

class LSAOpenException(LSAException2):
    """
    Raised when open fails.
    """
    pass

class LSACloseException(LSAException2):
    """
    Raised when the cnx is already closed or was never open.
    """
    pass

class LSALookUpNamesException(LSAException2):
    """
    Raised when an error was detected.
    """
    pass

class LSALookUpSidsException(LSAException2):
    """
    Raised when an error was detected.
    """
    pass

#######################################################################
#####
##### Main classes: LSA, LSAClient (LSAServer will not be implemented)
##### API will raise specific exceptions when errors are caught.
#######################################################################

class LSA():
    def __init__(self, host, port=445):
        self.host              = host
        self.port              = port
        self.is_unicode        = True
        self.policy_handle     = None
        self.uuid              = (u'12345778-1234-abcd-ef00-0123456789ab', u'0.0')

class LSAClient(LSA):

    def __init__(self, host, port=445):
        LSA.__init__(self, host, port)
        self.username = None
        self.password = None
        self.domain = None
        self.kerberos_db = None
        self.use_krb5 = False

    def set_credentials(self, username=None, password=None, domain=None, kerberos_db=None, use_krb5=False):
        if username:
            self.username = username
        if password:
            self.password = password
        if domain:
            self.domain = domain
        if kerberos_db:
            self.kerberos_db = kerberos_db
            self.use_krb5 = True
        else:
            if use_krb5:
                self.use_krb5 = use_krb5

    def __bind_krb5(self, connector):

        try:
            self.dce = DCERPC(connector,
                              getsock=None,
                              username=self.username,
                              password=self.password,
                              domain=self.domain,
                              kerberos_db=self.kerberos_db,
                              use_krb5=True)

            return self.dce.bind(self.uuid[0], self.uuid[1], RPC_C_AUTHN_WINNT, RPC_C_AUTHN_LEVEL_PKT_INTEGRITY)
        except Exception as e:
            return 0

    def __bind_ntlm(self, connector):

        try:
            self.dce = DCERPC(connector,
                              getsock=None,
                              username=self.username,
                              password=self.password,
                              domain=self.domain,
                              use_krb5=False)

            return self.dce.bind(self.uuid[0], self.uuid[1], RPC_C_AUTHN_WINNT, RPC_C_AUTHN_LEVEL_PKT_INTEGRITY)
        except Exception as e:
            return 0

    def __bind(self, connector):

        if self.use_krb5:
            ret = self.__bind_krb5(connector)
            if not ret:
                return self.__bind_ntlm(connector)
        else:
            ret = self.__bind_ntlm(connector)
            if not ret:
                return self.__bind_krb5(connector)
        return 1

    def bind(self):
        """
        Perform a binding with the server.
        0 is returned on failure.
        """

        connectionlist = []
        connectionlist.append(u'ncacn_np:%s[\\lsarpc]' % self.host)
        connectionlist.append(u'ncacn_ip_tcp:%s[%d]' % (self.host,self.port))
        connectionlist.append(u'ncacn_tcp:%s[%d]' % (self.host,self.port))

        for connector in connectionlist:
            ret = self.__bind(connector)
            if ret:
                return 1

        return 0

    def get_reply(self):
        return self.dce.reassembled_data

    def open(self):
        """
        Gets a policy handle to perform other calls.
        LSAOpenException is raised on failure.
        """
        try:
            data = LSAOpenPolicy2Request(SystemName='\\\\' + self.host, DesiredAccess=LSA_POLICY_LOOKUP_NAMES).pack()
        except Exception as e:
            raise LSAOpenException('LSAOpenPolicy() failed to build the request.')

        self.dce.call(LSA_COM_OPEN_POLICY2, data, response=True)
        if len(self.get_reply()) < 4:
            raise LSAOpenException('LSAOpenPolicy() call was not correct.')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:
                resp = LSAOpenPolicy2Response(self.get_reply())
                policy_handle = resp.get_handle()
                self.policy_handle = policy_handle
                return policy_handle
            except Exception as e:
                raise LSAOpenException('LSAOpenPolicy() failed: Parsing error in the answer.')
        else:
            raise LSAOpenException('LSAOpenPolicy() failed.', status=status)

    def close(self):
        """
        Destroy the policy handle.
        LSACloseException is raised on failure.
        """

        if not self.policy_handle:
            raise LSACloseException('LSAClose() failed because no policy handle could be found.')

        try:
            data = LSACloseRequest(PolicyHandle=self.policy_handle).pack()
        except Exception as e:
            raise LSACloseException('LSAClose() failed to build the request.')

        self.dce.call(LSA_COM_CLOSE, data, response=True)
        if len(self.get_reply()) < 4:
            raise LSACloseException('LSAClose() call was not correct.')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:
                resp = LSACloseResponse(self.get_reply())
                self.policy_handle = None
            except Exception as e:
                raise LSACloseException('LSAClose() failed: Parsing error in the answer.')
        else:
            raise LSACloseException('LSAClose() failed.', status=status)

    def __lookup_names(self, names):
        """
        Return the Sids corresponding to the list of names.
        LSALookUpNamesException is raised on failure.
        """
        do_close=0
        if not self.policy_handle:
            do_close=1
            self.open()

        try:
            data = LSALookupNamesRequest(PolicyHandle=self.policy_handle, NamesArray=names).pack()
        except Exception as e:
            raise LSALookUpNamesException('LSALookupNames() failed to build the request.')

        self.dce.call(LSA_COM_LOOKUP_NAMES, data, response=True)
        answ_str = self.get_reply()
        if len(answ_str) < 4:
            raise LSALookUpNamesException('LSALookupNames() call was not correct.')

        status = unpack('<L', answ_str[-4:])[0]
        if do_close:
            self.close()
        if status == 0:
            try:
                resp = LSALookupNamesResponse(answ_str)
                return resp.get_sids()
            except Exception as e:
                raise LSALookUpNamesException('LSALookUpNames() failed: Parsing error in the answer.')
        else:
            raise LSALookUpNamesException('LSALookUpNames() failed.', status=status)

    def __lookup_names3(self, names):
        """
        Return the Sids corresponding to the list of names.
        LSALookUpNamesException is raised on failure.
        """
        do_close=0
        if not self.policy_handle:
            do_close=1
            self.open()

        try:
            data = LSALookupNames3Request(PolicyHandle=self.policy_handle, NamesArray=names).pack()
        except Exception as e:
            raise LSALookUpNamesException('LSALookupNames() failed to build the request.')

        self.dce.call(LSA_COM_LOOKUP_NAMES3, data, response=True)
        answ_str = self.get_reply()

        if len(answ_str) < 4:
            raise LSALookUpNamesException('LSALookupNames() call was not correct.')

        status = unpack('<L', answ_str[-4:])[0]
        if do_close:
            self.close()
        if status == 0:
            try:
                resp = LSALookupNames3Response(answ_str)
                return resp.get_sids()
            except Exception as e:
                raise LSALookUpNamesException('LSALookUpNames() failed: Parsing error in the answer.')
        else:
            raise LSALookUpNamesException('LSALookUpNames() failed.', status=status)

    def lookup_names(self, names, version=0):
        """
        Return the Sids corresponding to the list of names.
        LSALookUpNamesException is raised on failure.
        """
        if version == 3:
            return self.__lookup_names3(names)
        else:
            return self.__lookup_names(names)

    def lookup_sids(self, sids):
        """
        Return the Names corresponding to the list of Sids.
        LSALookUpSidsException is raised on failure.
        """
        do_close=0
        if not self.policy_handle:
            do_close=1
            self.open()

        try:
            data = LSALookupSidsRequest(PolicyHandle=self.policy_handle, Sids=sids).pack()
        except Exception as e:
            raise LSALookUpSidsException('lookup_sids() failed to build the request.')

        self.dce.call(LSA_COM_LOOKUP_SIDS, data, response=True)
        answ_str = self.get_reply()
        if len(answ_str) < 4:
            raise LSALookUpSidsException('lookup_sids() call was not correct.')

        status = unpack('<L', answ_str[-4:])[0]
        if do_close:
            self.close()
        # We may need to provide more than 1 SID. Typically this appends when one
        # bruteforces SID (this can be done in 1 request). However since not all
        # the SID requested may exist, the API may return STATUS_SOME_NOT_MAPPED
        # aka 0x107 error.
        if status == 0 or status == 0x107:
            try:
                resp = LSALookupSidsResponse(answ_str)
                names = resp.get_names()
                # This shouldn't be possible, but just in case...
                if len(names) != len(sids):
                    return names
                # Adds the Sid information as well.
                for i in xrange(len(sids)):
                    names[i]['Sid'] = sids[i]
                return names
            except Exception as e:
                raise LSALookUpSidsException('lookup_sids() failed: Parsing error in the answer.')
        else:
            raise LSALookUpSidsException('lookup_sids() failed.', status=status)

    def lookup_sids_with_domains(self, sids):
        """
        Return the Names and associated Domains corresponding to the list of Sids.
        LSALookUpSidsException is raised on failure.
        """
        do_close=0
        if not self.policy_handle:
            do_close=1
            self.open()

        try:
            data = LSALookupSidsRequest(PolicyHandle=self.policy_handle, Sids=sids).pack()
        except Exception as e:
            raise LSALookUpSidsException('lookup_sids() failed to build the request.')

        self.dce.call(LSA_COM_LOOKUP_SIDS, data, response=True)
        answ_str = self.get_reply()
        if len(answ_str) < 4:
            raise LSALookUpSidsException('lookup_sids() call was not correct.')

        status = unpack('<L', answ_str[-4:])[0]
        if do_close:
            self.close()
        # We may need to provide more than 1 SID. Typically this appends when one
        # bruteforces SID (this can be done in 1 request). However since not all
        # the SID requested may exist, the API may return STATUS_SOME_NOT_MAPPED
        # aka 0x107 error.
        if status == 0 or status == 0x107:
            try:
                resp = LSALookupSidsResponse(answ_str)
                names = resp.get_names()
                domains = resp.get_domains()
                # This shouldn't be possible, but just in case...
                if len(names) != len(sids):
                    return names
                # Adds the Sid information as well.
                for i in xrange(len(sids)):
                    names[i]['Sid'] = sids[i]
                return names, domains
            except Exception as e:
                raise LSALookUpSidsException('lookup_sids() failed: Parsing error in the answer.')
        else:
            raise LSALookUpSidsException('lookup_sids() failed.', status=status)

    def lookup_domains(self, names = ['Administrator']):
        """
        Return the names & sids of the domains managed by the AD
        LSALookUpNamesException is raised on failure.
        """

        # The trick is that Administrator will always exist so the LSALookupNames3()
        # API will answer leaking the domains.

        do_close=0
        if not self.policy_handle:
            do_close=1
            try:
                self.open()
            except Exception as e:
                raise LSALookUpNamesException('lookup_domains() failed.')

        try:
            data = LSALookupNames3Request(PolicyHandle=self.policy_handle, NamesArray=names).pack()
        except Exception as e:
            raise LSALookUpNamesException('lookup_domains() failed to build the request.')

        self.dce.call(LSA_COM_LOOKUP_NAMES3, data, response=True)
        answ_str = self.get_reply()

        if len(answ_str) < 4:
            raise LSALookUpNamesException('lookup_domains() call was not correct.')

        status = unpack('<L', answ_str[-4:])[0]
        if do_close:
            self.close()
        if status == 0:
            try:
                resp = LSALookupNames3Response(answ_str)
                return resp.get_domains()
            except Exception as e:
                raise LSALookUpNamesException('lookup_domains() failed: Parsing error in the answer.')
        else:
            raise LSALookUpNamesException('lookup_domains() failed.', status=status)

#######################################################################
#####
##### A couple of useful functions for other parts of CANVAS
#####
#######################################################################

def lsa_get_user_sid(ad_ip, account_name='Administrator', username=None, password=None, domain=None):
    try:
        lsa = LSAClient(ad_ip)
        lsa.set_credentials(username, password, domain)
        if not lsa.bind():
            return None
        names = lsa.lookup_names([account_name])
        return names[0]['Sid']
    except Exception as e:
        logging.error('LSARPC_ERROR: %s' % str(e))
        return None

def lsa_get_user_rid(ad_ip, account_name='Administrator', account_sid=None, username=None, password=None, domain=None):

    if not account_sid:
        account_sid = lsa_get_user_sid(ad_ip, account_name, username, password, domain)
    try:
        x,y = account_sid.rsplit('-', 1)
        rid = int(y)
        return rid
    except Exception as e:
        logging.error('LSARPC_ERROR: %s' % str(e))
        return None

def lsa_get_domains(ad_ip, username=None, password=None, domain=None):
        lsa = LSAClient(ad_ip)
        lsa.set_credentials(username, password, domain)
        if not lsa.bind():
            return None
        try:
            domains = lsa.lookup_domains()
            return domains
        except Exception as e:
            logging.error('LSARPC_ERROR: %s' % str(e))
            return None

def lsa_get_domain_sid(ad_ip, domain_name, username=None, password=None, domain=None):
        domains = lsa_get_domains(ad_ip, username, password, domain)
        if domains == None or not len(domains):
            return None
        # Just in case we still add the try/catch block
        try:
            for dom in domains:
                if dom['Name'].upper() == domain_name.upper():
                    return dom['Sid']
                if '.' in domain_name:
                    dom_stripped = domain_name.rsplit('.',1)[0]
                    if str(dom_stripped).upper() == dom['Name'].upper():
                        return dom['Sid']
            return None
        except Exception as e:
            logging.error('LSARPC_ERROR: %s' % str(e))
            return None

#######################################################################
#####
##### Well, the main :D
#####
#######################################################################

SERVER_IP   = '10.0.0.1'
ADMIN_USER  = 'administrator'
ADMIN_PASS  = 'foobar123!'
NORMAL_USER = 'jojo1'
NORMAL_PASS = 'foobar1234!'
DOMAIN      = 'immu5.lab'

def main():

    logging.info('[+] Performing test1...')
    lsa = LSAClient(SERVER_IP)
    lsa.set_credentials(ADMIN_USER, ADMIN_PASS, DOMAIN)
    if not lsa.bind():
        logging.error('bind() failed.')
        sys.exit(0)
    try:
        names = lsa.lookup_names([NORMAL_USER], version=3)
        logging.info('\t-> Names = %s' % str(names))
    except Exception as e:
        logging.error('[-] Error: %s' % str(e))

    logging.info('[+] Performing test2...')
    names = lsa_get_domains(SERVER_IP,
                            NORMAL_USER,
                            NORMAL_PASS,
                            DOMAIN)
    logging.info('\t-> Names = %s' % str(names))

    logging.info('[+] Performing test3...')
    sid = lsa_get_domain_sid(SERVER_IP,
                             DOMAIN,
                             username=NORMAL_USER,
                             password=NORMAL_PASS,
                             domain=DOMAIN)
    logging.info('\t-> SID = %s' % sid)

    logging.info('[+] Performing test4...')
    rid = lsa_get_user_rid(SERVER_IP,
                           account_name=ADMIN_USER,
                           account_sid=None,
                           username=NORMAL_USER,
                           password=NORMAL_PASS,
                           domain=DOMAIN)
    logging.info('\t-> RID = %s' % rid)

    logging.info('[+] Performing test5...')
    sid = lsa_get_user_sid(SERVER_IP,
                           ADMIN_USER,
                           username=NORMAL_USER,
                           password=NORMAL_PASS,
                           domain=DOMAIN)
    logging.info('\t-> SID = %s' % sid)
    sys.exit(0)

if __name__ == "__main__":

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == '-v':
        logger.setLevel(logging.DEBUG)

    main()

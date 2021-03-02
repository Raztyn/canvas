#!/usr/bin/env python
##ImmunityHeader v1
###############################################################################
## File       :  drsupai.py
## Description:
##            :
## Created_On :  Wed Sep 23 CEST 2015
## Created_By :  X.
##
## (c) Copyright 2010, Immunity, Inc. all rights reserved.
###############################################################################

# The API is not 100% written but is currently working quite well.
# Implemented from:
#
#    + Wireshark (Integrity forced)
#    + [MS-DRSR].pdf
#    + [MS-SAMR].pdf
#    + http://github.com/CoreSecurity/impacket

import sys
import logging
import hashlib
from struct import pack, unpack

if '.' not in sys.path:
    sys.path.append('.')

from libs.newsmb.epmap_ng import EPTClient
from libs.newsmb.libdcerpc import DCERPC, DCERPCString, DCERPCSid, DCERPCGuid
from libs.newsmb.libdcerpc import RPC_C_AUTHN_WINNT
from libs.newsmb.libdcerpc import RPC_C_AUTHN_LEVEL_PKT_PRIVACY
from libs.newsmb.libdcerpc import RPC_C_AUTHN_LEVEL_PKT_INTEGRITY
from libs.newsmb.samr import DeriveKeyFromLittleEndian
from libs.newsmb.Struct import Struct
from libs.Crypto.Cipher import DES
from Crypto.Cipher import ARC4

try:
    from pyasn1.type import univ, tag
    from pyasn1.codec.ber import decoder,encoder
except ImportError:
    print "[EE] drsuapi: Cannot import pyasn1 (required)"
    raise

###
# Constants
###

# The RPC methods

DRSUPAI_COM_DS_BIND                       = 0
DRSUPAI_COM_DS_UNBIND                     = 1
DRSUPAI_COM_DS_REPLICA_SYNC               = 2
DRSUPAI_COM_DS_GET_NC_CHANGES             = 3
DRSUPAI_COM_DS_REPLICA_UPDATE_REFS        = 4
DRSUPAI_COM_DS_CRACK_NAMES                = 12
DRSUPAI_COM_DS_GET_DOMAIN_CONTROLLER_INFO = 16

# Errors returned by the API.
# Note: With proper namespace, they won't collide with other API

ERROR_INVALID_PARAMETER = 0x57
ERROR_DS_DRA_BAD_NC     = 0x20F8 # Usually means the name doesn't exist (anymore?)


# GUIDs

NTDSAPI_CLIENT_GUID = 'e24d201a-4fd6-11d1-a3da-0000f875ae0d'  # 5.138 NTSAPI_CLIENT_GUID
NULLGUID            = '00000000-0000-0000-0000-000000000000'  # 5.140 NULLGUID

# 5.39 DRS_EXTENSIONS_INT - flag field

DRS_EXT_BASE                         = 0x00000001
DRS_EXT_ASYNCREPL                    = 0x00000002
DRS_EXT_REMOVEAPI                    = 0x00000004
DRS_EXT_MOVEREQ_V2                   = 0x00000008
DRS_EXT_GETCHG_DEFLATE               = 0x00000010
DRS_EXT_DCINFO_V1                    = 0x00000020
DRS_EXT_RESTORE_USN_OPTIMIZATION     = 0x00000040
DRS_EXT_ADDENTRY                     = 0x00000080
DRS_EXT_KCC_EXECUTE                  = 0x00000100
DRS_EXT_ADDENTRY_V2                  = 0x00000200
DRS_EXT_LINKED_VALUE_REPLICATION     = 0x00000400
DRS_EXT_DCINFO_V2                    = 0x00000800
DRS_EXT_INSTANCE_TYPE_NOT_REQ_ON_MOD = 0x00001000
DRS_EXT_CRYPTO_BIND                  = 0x00002000
DRS_EXT_GET_REPL_INFO                = 0x00004000
DRS_EXT_STRONG_ENCRYPTION            = 0x00008000
DRS_EXT_DCINFO_VFFFFFFFF             = 0x00010000
DRS_EXT_TRANSITIVE_MEMBERSHIP        = 0x00020000
DRS_EXT_ADD_SID_HISTORY              = 0x00040000
DRS_EXT_POST_BETA3                   = 0x00080000
DRS_EXT_GETCHGREQ_V5                 = 0x00100000
DRS_EXT_GETMEMBERSHIPS2              = 0x00200000
DRS_EXT_GETCHGREQ_V6                 = 0x00400000
DRS_EXT_NONDOMAIN_NCS                = 0x00800000
DRS_EXT_GETCHGREQ_V8                 = 0x01000000
DRS_EXT_GETCHGREPLY_V5               = 0x02000000
DRS_EXT_GETCHGREPLY_V6               = 0x04000000
DRS_EXT_WHISTLER_BETA3               = 0x08000000
DRS_EXT_W2K3_DEFLATE                 = 0x10000000
DRS_EXT_GETCHGREQ_V10                = 0x20000000
DRS_EXT_RESERVED1                    = 0x40000000
DRS_EXT_RESERVED2                    = 0x80000000

# 5.39 DRS_EXTENSIONS_INT - flag_ext field

DRS_EXT_ADAM                         = 0x00000001
DRS_EXT_LH_BETA2                     = 0x00000002
DRS_EXT_RECYCLE_BIN                  = 0x00000004
DRS_EXT_GETCHGREPLY_V9               = 0x00000100

# 5.41 DRS_OPTIONS

DRS_ASYNC_OP                  = 0x00000001
DRS_GETCHG_CHECK              = 0x00000002
DRS_UPDATE_NOTIFICATION       = 0x00000002
DRS_ADD_REF                   = 0x00000004
DRS_SYNC_ALL                  = 0x00000008
DRS_DEL_REF                   = 0x00000008
DRS_WRIT_REP                  = 0x00000010
DRS_INIT_SYNC                 = 0x00000020
DRS_PER_SYNC                  = 0x00000040
DRS_MAIL_REP                  = 0x00000080
DRS_ASYNC_REP                 = 0x00000100
DRS_IGNORE_ERROR              = 0x00000100
DRS_TWOWAY_SYNC               = 0x00000200
DRS_CRITICAL_ONLY             = 0x00000400
DRS_GET_ANC                   = 0x00000800
DRS_GET_NC_SIZE               = 0x00001000
DRS_LOCAL_ONLY                = 0x00001000
DRS_NONGC_RO_REP              = 0x00002000
DRS_SYNC_BYNAME               = 0x00004000
DRS_REF_OK                    = 0x00004000
DRS_FULL_SYNC_NOW             = 0x00008000
DRS_NO_SOURCE                 = 0x00008000
DRS_FULL_SYNC_IN_PROGRESS     = 0x00010000
DRS_FULL_SYNC_PACKET          = 0x00020000
DRS_SYNC_REQUEUE              = 0x00040000
DRS_SYNC_URGENT               = 0x00080000
DRS_REF_GCSPN                 = 0x00100000
DRS_NO_DISCARD                = 0x00100000
DRS_NEVER_SYNCED              = 0x00200000
DRS_SPECIAL_SECRET_PROCESSING = 0x00400000
DRS_INIT_SYNC_NOW             = 0x00800000
DRS_PREEMPTED                 = 0x01000000
DRS_SYNC_FORCED               = 0x02000000
DRS_DISABLE_AUTO_SYNC         = 0x04000000
DRS_DISABLE_PERIODIC_SYNC     = 0x08000000
DRS_USE_COMPRESSION           = 0x10000000
DRS_NEVER_NOTIFY              = 0x20000000
DRS_SYNC_PAS                  = 0x40000000
DRS_GET_ALL_GROUP_MEMBERSHIP  = 0x80000000

# 4.1.10.2.21 EXOP_REQ Codes

EXOP_FSMO_REQ_ROLE      = 0x00000001
EXOP_FSMO_REQ_RID_ALLOC = 0x00000002
EXOP_FSMO_RID_REQ_ROLE  = 0x00000003
EXOP_FSMO_REQ_PDC       = 0x00000004
EXOP_FSMO_ABANDON_ROLE  = 0x00000005
EXOP_REPL_OBJ           = 0x00000006
EXOP_REPL_SECRETS       = 0x00000007

# 4.1.4.1.3 DS_NAME_FORMAT

DS_UNKNOWN_NAME            = 0
DS_FQDN_1779_NAME          = 1
DS_NT4_ACCOUNT_NAME        = 2
DS_DISPLAY_NAME            = 3
DS_UNIQUE_ID_NAME          = 6
DS_CANONICAL_NAME          = 7
DS_USER_PRINCIPAL_NAME     = 8
DS_CANONICAL_NAME_EX       = 9
DS_SERVICE_PRINCIPAL_NAME  = 10
DS_SID_OR_SID_HISTORY_NAME = 11
DS_DNS_DOMAIN_NAME         = 12

# 4.1.4.1.2 DRS_MSG_CRACKREQ_V1 - dwFlags

DS_NAME_FLAG_GCVERIFY             = 0x00000004
DS_NAME_FLAG_TRUST_REFERRAL       = 0x00000008
DS_NAME_FLAG_PRIVATE_RESOLVE_FPOS = 0x80000000

# 4.1.4.1.2 DRS_MSG_CRACKREQ_V1 - formatOffered

DS_LIST_SITES                       = 0xFFFFFFFF
DS_LIST_SERVERS_IN_SITE             = 0xFFFFFFFE
DS_LIST_DOMAINS_IN_SITE             = 0xFFFFFFFD
DS_LIST_SERVERS_FOR_DOMAIN_IN_SITE  = 0xFFFFFFFC
DS_LIST_INFO_FOR_SERVER             = 0xFFFFFFFB
DS_LIST_ROLES                       = 0xFFFFFFFA
DS_NT4_ACCOUNT_NAME_SANS_DOMAIN     = 0xFFFFFFF9
DS_MAP_SCHEMA_GUID                  = 0xFFFFFFF8
DS_LIST_DOMAINS                     = 0xFFFFFFF7
DS_LIST_NCS                         = 0xFFFFFFF6
DS_ALT_SECURITY_IDENTITIES_NAME     = 0xFFFFFFF5
DS_STRING_SID_NAME                  = 0xFFFFFFF4
DS_LIST_SERVERS_WITH_DCS_IN_SITE    = 0xFFFFFFF3
DS_LIST_GLOBAL_CATALOG_SERVERS      = 0xFFFFFFF1
DS_NT4_ACCOUNT_NAME_SANS_DOMAIN_EX  = 0xFFFFFFF0
DS_USER_PRINCIPAL_NAME_AND_ALTSECID = 0xFFFFFFEF

# 4.1.4.1.8 DS_NAME_ERROR

DS_NAME_NO_ERROR                        = 0
DS_NAME_ERROR_RESOLVING                 = 1
DS_NAME_ERROR_NOT_FOUND                 = 2
DS_NAME_ERROR_NOT_UNIQUE                = 3
DS_NAME_ERROR_NO_MAPPING                = 4
DS_NAME_ERROR_DOMAIN_ONLY               = 5
DS_NAME_ERROR_TRUST_REFERRAL            = 7
DS_NAME_ERROR_IS_SID_HISTORY_UNKNOWN    = 0xFFFFFFF2
DS_NAME_ERROR_IS_SID_HISTORY_ALIAS      = 0xFFFFFFF3
DS_NAME_ERROR_IS_SID_HISTORY_GROUP      = 0xFFFFFFF4
DS_NAME_ERROR_IS_SID_HISTORY_USER       = 0xFFFFFFF5
DS_NAME_ERROR_IS_SID_UNKNOWN            = 0xFFFFFFF6
DS_NAME_ERROR_IS_SID_ALIAS              = 0xFFFFFFF7
DS_NAME_ERROR_IS_SID_GROUP              = 0xFFFFFFF8
DS_NAME_ERROR_IS_SID_USER               = 0xFFFFFFF9
DS_NAME_ERROR_SCHEMA_GUID_CONTROL_RIGHT = 0xFFFFFFFA
DS_NAME_ERROR_SCHEMA_GUID_CLASS         = 0xFFFFFFFB
DS_NAME_ERROR_SCHEMA_GUID_ATTR_SET      = 0xFFFFFFFC
DS_NAME_ERROR_SCHEMA_GUID_ATTR          = 0xFFFFFFFD
DS_NAME_ERROR_SCHEMA_GUID_NOT_FOUND     = 0xFFFFFFFE
DS_NAME_ERROR_IS_FPO                    = 0xFFFFFFFF

# 4.1.10.2.20 EXOP_ERR Codes

EXOP_ERR_SUCCESS               = 0x00000001
EXOP_ERR_UNKNOWN_OP            = 0x00000002
EXOP_ERR_FSMO_NOT_OWNER        = 0x00000003
EXOP_ERR_UPDATE_ERR            = 0x00000004
EXOP_ERR_EXCEPTION             = 0x00000005
EXOP_ERR_UNKNOWN_CALLER        = 0x00000006
EXOP_ERR_RID_ALLOC             = 0x00000007
EXOP_ERR_FSMO_OWNER_DELETED    = 0x00000008
EXOP_ERR_FSMO_PENDING_OP       = 0x00000009
EXOP_ERR_MISMATCH              = 0x0000000A
EXOP_ERR_COULDNT_CONTACT       = 0x0000000B
EXOP_ERR_FSMO_REFUSING_ROLES   = 0x0000000C
EXOP_ERR_DIR_ERROR             = 0x0000000D
EXOP_ERR_FSMO_MISSING_SETTINGS = 0x0000000E
EXOP_ERR_ACCESS_DENIED         = 0x0000000F
EXOP_ERR_PARAM_ERROR           = 0x00000010

# 5.53 ENTINF

ENTINF_FROM_MASTER    = 0x00000001
ENTINF_DYNAMIC_OBJECT = 0x00000002
ENTINF_REMOTE_MODIFY  = 0x00010000

###
# DRSUPI Objects.
# No exception handling for these objects.
###

"""
5.40 DRS_HANDLE
---------------

typedef [context_handle] void* DRS_HANDLE;
Actually a 20 bytes buffer
"""

class DrsHandle(Struct):
    st = [
        ['handle', '20s', '\x00'*20],
    ]

    def __init__(self, data=None, handle='', is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['handle'] = handle

    def pack(self):
        data = Struct.pack(self)
        return data


"""
5.143 OID_t
-----------

typedef struct {
    [range(0,10000)] unsigned int length;
    [size_is(length)] BYTE* elements;
} OID_t;
"""

class DrsOid(Struct):
    st = [
        ['length', '<L', 0],
        ['elements', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['length'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['elements'] = data[pos:pos+self['length']]
        else:
            pass
            # TODO

    def get_raw(self):
        l = len(self['elements'])
        if l >= 128:
            return ''
        return '\x06' + chr(l) + self['elements']

    def get_oid(self):
        l = len(self['elements'])
        if l >= 128:
            return ''
        raw = '\x06' + chr(l) + self['elements']
        return str(decoder.decode(raw)[0])

    def calcsize(self):
        return len(self.pack())

    def pack(self):
        data  = Struct.pack(self)
        data += self['elements']
        if len(data)%4:
            data += 'x'*(4-(len(data)%4))
        return data


"""
5.154 PrefixTableEntry
----------------------

typedef struct {
    unsigned long ndx;
    OID_t prefix;
} PrefixTableEntry;
"""

class DrsPrefixTableEntry(Struct):
    st = [
        ['ndx', '<L', 0],
        ['prefix', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.size = 0
        self.ptr  = 0x2004

        if data is not None:
            pos = 0
            self['ndx'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.size = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.ptr = unpack('<L', data[pos:pos+4])[0]
        else:
            pass
            # TODO

    def calcsize(self):
        return 4*3

    def pack(self):
        data  = pack('<L', self['ndx'])
        data += pack('<L', self.size)
        data += pack('<L', self.ptr)
        return data

# Fictional struct, used mostly for unpacking.
class DrsPrefixTableEntryArray(Struct):
    st = [
        ['PrefixCount', '<L', 0],
        ['PrefixEntries', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.headers = []
        self.entries = []

        # Note: Currently doesn't handle NULL ptr
        if data is not None:
            pos = 0
            self['PrefixCount'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            for i in xrange(self['PrefixCount']):
                h = DrsPrefixTableEntry(data=data[pos:])
                pos += h.calcsize()
                self.headers.append(h)
            for i in xrange(self['PrefixCount']):
                e = DrsOid(data=data[pos:])
                pos += e.calcsize()
                self.entries.append(e)
        else:
            pass
            # TODO

    def get_elements(self):
        return self.entries

    # This structure has a variable size
    def calcsize(self):
        size = 4
        for h in self.headers:
            size += h.calcsize()
        for e in self.entries:
            size += e.calcsize()
        return size

    def pack(self):
        s  = pack('<L', self['PrefixCount'])
        for h in headers:
            data += h.pack()
        for e in entries:
            data += e.pack()
        return data


"""
5.180 SCHEMA_PREFIX_TABLE
-------------------------

typedef struct {
    [range(0,1048576)] DWORD PrefixCount;
    [size_is(PrefixCount)] PrefixTableEntry* pPrefixEntry;
} SCHEMA_PREFIX_TABLE;
"""

class DrsSchemaPrefixTable(Struct):
    st = [
        ['PrefixCount', '<L', 1],
        ['PrefixEntry', '0s', ''],
    ]

    def __init__(self, data=None, PrefixEntry='', is_unicode=True):
        Struct.__init__(self, data)
        self.pPrefixEntry = 0x00020010

        if data is not None:
            pos = 0
            self['PrefixCount'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pPrefixEntry = unpack('<L', data[pos:pos+4])[0]

        else:
            pass
            # TODO

    def is_empty(self):
        return self.pPrefixEntry == 0

    def pack(self):
        data  = pack('<L', self['PrefixCount'])
        data += pack('<L', self.pPrefixEntry)
        return data


"""
5.16 ATTRVAL
------------

typedef struct {
    [range(0,26214400)] ULONG valLen;
    [size_is(valLen)] UCHAR* pVal;
} ATTRVAL;
"""

class DrsAttrVal(Struct):
    st = [
        ['valLen', '<L', 0],
        ['pVal', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.pAval = 0x00020004

        if data is not None:
            pos = 0
            self['valLen'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['pVal'] = data[pos:pos+self['valLen']]

        else:
            pass
            # TODO

    def get_raw(self):
        return self['pVal']

    def get_length(self):
        return len(self['pVal'])

    def calcsize(self):
        size = self['valLen']
        if size%4:
            size += (4-size%4)
        return 4+size

    def pack(self):

        data  = pack('<L', self['valLen'])
        data += self['pVal']
        if len(data)%4:
            data += 'x'*(4-len(data)%4)
        return data

# This structure doesn't really exist.
class DrsAttrValArray(Struct):
    st = [
        ['valCount', '<L', 0],
        ['values', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self['values'] = []

        if data is not None:
            pos = 4
            for i in xrange(self['valCount']):
                length = unpack('<L', data[pos:pos+4])[0]
                pos += 4
                ptr = unpack('<L', data[pos:pos+4])[0]
                pos += 4
                self['values'].append({'pValue':ptr, 'length':length})
            for i in xrange(self['valCount']):
                val = DrsAttrVal(data=data[pos:])
                pos += val.calcsize()
                self['values'][i]['data'] = val
        else:
            pass
            # TODO

    def get_nbr_values(self):
        return self['valCount']

    def get_values(self):
        return self['values']

    def calcsize(self):
        size = 4 + self['valCount'] * (4*2)
        for val in self['values']:
            len_val = val['data'].calcsize()
            size += len_val
        return size

    def pack(self):

        data  = pack('<L', self['valCount'])
        for i in xrange(self['valCount']):
            data += pack('<L', self['values'][i]['length'] )
            data += pack('<L', 0x20004+4*i)
        for i in xrange(self['valCount']):
            data += self['values'][i]['data'].pack()
        return data


"""
5.17 ATTRVALBLOCK
-----------------

typedef struct {
    [range(0,10485760)] ULONG valCount;
    [size_is(valCount)] ATTRVAL* pAVal;
} ATTRVALBLOCK;
"""

class DrsAttrValBlock(Struct):
    st = [
        ['valCount', '<L', 0],
        ['pAval', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.pAval = 0x00020004

        if data is not None:
            pos = 0
            self['valCount'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pAval = unpack('<L', data[pos:pos+4])[0]
        else:
            pass
            # TODO

    def get_nbr_values(self):
        return self['valCount']

    def calcsize(self):
        return 8

    def pack(self):

        data  = pack('<L', self['valCount'])
        data += pack('<L', self.pAval)
        return data


"""
5.9 ATTR
--------

typedef struct {
    ATTRTYP attrTyp;
    ATTRVALBLOCK AttrVal;
} ATTR;
"""

class DrsAttr(Struct):
    st = [
        ['attrTyp', '<L', 0],
        ['AttrVal', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['attrTyp'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['AttrVal'] = DrsAttrValBlock(data[pos:])

        else:
            pass
            # TODO

    def get_type(self):
        return self['attrTyp']

    def get_value(self):
        return self['AttrVal']

    def calcsize(self):
        return 4 + self['AttrVal'].calcsize()

    def pack(self):

        data  = pack('<L', self['attrTyp'])
        data += self['AttrVal'].pack()
        return data


"""
5.10 ATTRBLOCK
--------------

typedef struct {
    [range(0,1048576)] ULONG attrCount;
    [size_is(attrCount)] ATTR* pAttr;
} ATTRBLOCK;
"""

class DrsAttrBlock(Struct):
    st = [
        ['attrCount', '<L', 0],
        ['pAttr', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.pAttr = 0x00020004

        if data is not None:
            pos = 0
            self['attrCount'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pAttr = unpack('<L', data[pos:pos+4])[0]

        else:
            pass
            # TODO

    def calcsize(self):
        return 8

    def pack(self):

        data  = pack('<L', self['ulFlags'])
        data += pack('<L', self.pAttr)
        return data


"""
5.53 ENTINF
-----------

typedef struct {
    DSNAME* pName;
    unsigned long ulFlags;
    ATTRBLOCK AttrBlock;
} ENTINF;
"""

class DrsEntInf(Struct):
    st = [
        ['pName', '0s', ''],
        ['ulFlags', '<L', 0],
        ['AttrBlock', '0s', ''],
    ]

    def __init__(self, data=None, PrefixEntry='', is_unicode=True):
        Struct.__init__(self, data)
        self.pName = 0x00020004

        if data is not None:
            pos = 0
            self.pName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['ulFlags'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['AttrBlock'] = DrsAttrBlock(data=data[pos:])

        else:
            pass
            # TODO

    def has_name(self):
        return self.pName != 0

    def calcsize(self):
        return 4 + 4 + self['AttrBlock'].calcsize()

    def pack(self):
        data  = pack('<L', self.pName)
        data  = pack('<L', self['ulFlags'])
        data += self['AttrBlock'].pack()
        return data


"""
5.162 REPLENTINFLIST
--------------------

typedef struct REPLENTINFLIST {
    struct REPLENTINFLIST* pNextEntInf;
    ENTINF Entinf;
    BOOL fIsNCPrefix;
    UUID* pParentGuid;
    PROPERTY_META_DATA_EXT_VECTOR* pMetaDataExt;
} REPLENTINFLIST;
"""

class DrsReplentInfList(Struct):
    st = [
        ['pNextEntInf', '0s', ''],
        ['Entinf', '0s', ''],
        ['fIsNCPrefix', '<L', 0],
        ['pParentGuid', '0s', ''],
        ['pMetaDataExt', '0s', ''],
    ]

    def __init__(self, data=None, PrefixEntry='', is_unicode=True):
        Struct.__init__(self, data)
        self.pNextEntInf = 0x00020004
        self.pParentGuidm = 0x00020008
        self.pMetaDataExt = 0x0002000c

        if data is not None:
            pos = 0
            self.pNextEntInf = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['Entinf'] = DrsEntInf(data=data[pos:])
            pos += self['Entinf'].calcsize()
            self['fIsNCPrefix'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pParentGuidm = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pMetaDataExt = unpack('<L', data[pos:pos+4])[0]

        else:
            pass
            # TODO

    def has_name(self):
        return self['Entinf'].has_name()

    def calcsize(self):
        return 4 + self['Entinf'].calcsize() + 4*3

    def pack(self):
        data  = pack('<L', self.pNextEntInf)
        data += self['Entinf'].pack()
        data  = pack('<L', self['fIsNCPrefix'])
        data += pack('<L', self.pParentGuidm)
        data += pack('<L', self.pMetaDataExt)
        return data


"""
5.146 PARTIAL_ATTR_VECTOR_V1_EXT
--------------------------------

typedef struct {
    DWORD dwVersion;
    DWORD dwReserved1;
    [range(1,1048576)] DWORD cAttrs;
    [size_is(cAttrs)] ATTRTYP rgPartialAttr[];
} PARTIAL_ATTR_VECTOR_V1_EXT;
"""

class DrsPartialAttrVectorV1Ext(Struct):
    st = [
        ['dwVersion', '<L', 1],
        ['dwReserved1', '<0', 0],
        ['cAttrs', '<0', 0],
        ['rgPartialAttr', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['cAttrs'] = 1
            self['rgPartialAttr'] = "abcd"

    def pack(self):
        data  = pack('<L', self['dwVersion'])
        data += pack('<L', self['dwReserved1'])
        data += pack('<L', self['cAttrs'])
        #data += self['PrefixCount'] ### NOK
        return data


# 5.39 DRS_EXTENSIONS_INT
class DrsExtensionsInt(Struct):
    st = [
        ['cb', '<L', 52],
        ['dwFlags', '<L', 0],
        ['SiteObjGuid', '0s', ''],
        ['Pid', '<L', 0],
        ['dwReplEpoch', '<L', 0],
        ['dwFlagsExt', '<L', 0],
        ['ConfigObjGUID', '0s', ''],
        ['dwExtCaps', '<L', 127 ],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['dwFlags'] = DRS_EXT_GETCHGREQ_V6 | DRS_EXT_GETCHGREPLY_V6 | DRS_EXT_GETCHGREQ_V8 | DRS_EXT_STRONG_ENCRYPTION
            self['SiteObjGuid'] = DCERPCGuid(guid=NULLGUID)
            self['ConfigObjGUID'] = DCERPCGuid(guid=NULLGUID)

    def pack(self):
        s  = pack('<L', self['dwFlags'])
        s += self['SiteObjGuid'].pack()
        s += pack('<L', self['Pid'])
        s += pack('<L', self['dwReplEpoch'])
        s += pack('<L', self['dwFlagsExt'])
        s += self['ConfigObjGUID'].pack()
        s += pack('<L', self['dwExtCaps'])
        self['cb'] = len(s)
        data = pack('<L', self['cb'])
        data += s
        return data

"""
5.38 DRS_EXTENSIONS
-------------------

typedef struct {
    [range(1,10000)] DWORD cb;
    [size_is(cb)] BYTE rgb[];
} DRS_EXTENSIONS;

Note: rdb = array of DRS_EXTENSIONS_INT
"""

class DrsExtensions(Struct):
    st = [
        ['cb', '<L', 0],
        ['rgb', '0s', ''],
    ]

    def __init__(self, data=None, drs_entensions=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            # TODO
        else:
            self['rgb'] = drs_entensions
            if drs_entensions:
                self['cb'] = len(drs_entensions.pack()) - 4

    def pack(self):
        data = pack('<L', self['cb'])
        if self['rgb']:
            data += self['rgb'].pack()
        return data


"""
5.50 DSNAME
-----------

typedef struct {
    unsigned long structLen;
    unsigned long SidLen;
    GUID Guid;
    NT4SID Sid;
    unsigned long NameLen;
    [range(0, 10485761), size_is(NameLen + 1)]
    WCHAR StringName[];
} DSNAME;
"""

class DrsName(Struct):
    st = [
        ['structLen', '<L', 0],
        ['SidLen', '<L', 0],
        ['Guid', '0s', ''],
        ['Sid', '0s', ''],
        ['NameLen', '<L', 0],
        ['StringName', '0s', ''],
    ]

    def __init__(self, data=None, username='Administrator', is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:

            # TODO: something wrong with the SID parsing.
            pos  = 0
            string_length = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['structLen'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['SidLen'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4

            pos = self['structLen'] - (2*string_length-2)
            self['StringName'] = data[pos:pos+2*string_length+2]

        else:
            self['SidLen'] = 0
            self['Guid'] = DCERPCGuid(guid=NULLGUID)
            self['Sid'] = '\x00'*28
            self['NameLen'] = len(username)
            self['StringName'] = (username+'\x00').encode('UTF-16LE')
            self['structLen'] = len(self.pack())

    def calcsize(self, padding=False):
        length = self['structLen'] + 4
        if padding and length%4:
            length += (4-length%4)
        return length

    def pack(self):

        data  = pack('<L', self['NameLen']+1)
        data += pack('<L', self['structLen'])
        data += pack('<L', self['SidLen'])
        data += self['Guid'].pack()
        data += self['Sid']
        data += pack('<L', self['NameLen'])
        data += self['StringName']
        return data


"""
5.209 USN_VECTOR
----------------

typedef LONGLONG USN;
typedef struct {
    USN usnHighObjUpdate;
    USN usnReserved;
    USN usnHighPropUpdate;
} USN_VECTOR;
"""

class DrsUsnVector(Struct):
    st = [
        ['usnHighObjUpdate', '<Q', 0],
        ['usnReserved', '<Q', 0],
        ['usnHighPropUpdate', '<Q', 0],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['usnHighObjUpdate'] = 0
            self['usnReserved'] = 0
            self['usnHighPropUpdate'] = 0

    def pack(self):
        return Struct.pack(self)


"""
5.201 UPTODATE_CURSOR_V1
------------------------

typedef struct {
    UUID uuidDsa;
    USN usnHighPropUpdate;
} UPTODATE_CURSOR_V1;
"""

class DrsUptodateCursorV1(Struct):
    st = [
        ['uuidDsa', '0s', ''],
        ['usnHighPropUpdate', '<Q', 0],
    ]

    def __init__(self, data=None, uuid='', is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            # TODO
        else:
            self['uuidDsa'] = DCERPCUuid(uuid=uuid)
            self['usnHighPropUpdate'] = 0

    def pack(self):
        data = self['uuidDsa'].pack()
        data += pack('<Q', self['usnHighPropUpdate'])
        return data


"""
4.1.10.2.1 DRS_MSG_GETCHGREQ
----------------------------

typedef
[switch_type(DWORD)]
union {
     [case(4)]
     DRS_MSG_GETCHGREQ_V4 V4;
     [case(5)]
     DRS_MSG_GETCHGREQ_V5 V5;
     [case(7)]
     DRS_MSG_GETCHGREQ_V7 V7;
     [case(8)]
     DRS_MSG_GETCHGREQ_V8 V8;
     [case(10)]
     DRS_MSG_GETCHGREQ_V10 V10;
} DRS_MSG_GETCHGREQ;
"""

# V8: Version 8 request (Windows Server 2003 RPC replication).
"""
7 Appendix A: Full IDL
----------------------

typedef struct {
     UUID uuidDsaObjDest;
     UUID uuidInvocIdSrc;
     [ref] DSNAME* pNC;
     USN_VECTOR usnvecFrom;
     [unique] UPTODATE_VECTOR_V1_EXT* pUpToDateVecDest;
     ULONG ulFlags;
     ULONG cMaxObjects;
     ULONG cMaxBytes;
     ULONG ulExtendedOp;
     ULARGE_INTEGER liFsmoInfo;
     [unique] PARTIAL_ATTR_VECTOR_V1_EXT* pPartialAttrSet;
     [unique] PARTIAL_ATTR_VECTOR_V1_EXT* pPartialAttrSetEx;
     SCHEMA_PREFIX_TABLE PrefixTableDest;
} DRS_MSG_GETCHGREQ_V8;
"""

class DrsMsgGetchgreqV8(Struct):
    st = [
        ['uuidDsaObjDest', '0s', ''],
        ['uuidInvocIdSrc', '0s', ''],
        ['pNC', '0s', ''],
        ['usnvecFrom', '0s', ''],
        ['pUpToDateVecDest', '0s', ''],
        ['ulFlags', '<L', DRS_INIT_SYNC|DRS_WRIT_REP],
        ['cMaxObjects', '<L', 1],
        ['cMaxBytes', '<L', 0],
        ['ulExtendedOp', '<L', EXOP_REPL_OBJ ],
        ['liFsmoInfo', '<Q', 0],
        ['pPartialAttrSet', '0s', ''],
        ['pPartialAttrSetEx', '0s', ''],
        ['PrefixTableDest', '0s', ''],
    ]

    def __init__(self, data=None, username='', NtdsDsaObjectGuid='\x00'*16, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['uuidDsaObjDest'] = NtdsDsaObjectGuid #DCERPCGuid(guid=NTDSAPI_CLIENT_GUID)
            self['uuidInvocIdSrc'] = NtdsDsaObjectGuid #DCERPCGuid(guid=NTDSAPI_CLIENT_GUID)
            self['pNC'] = DrsName(username=username)
            self['usnvecFrom'] = DrsUsnVector()
            self['pPartialAttrSet'] = DrsPartialAttrVectorV1Ext()
            self['PrefixTableDest'] = DrsSchemaPrefixTable(PrefixEntry='0')

    def pack(self):

        data  = pack('<L', 8) # version
        data += pack('<L', 0xabababab) # ALIGN
        data += self['uuidDsaObjDest']#.pack() #TODO
        data += self['uuidInvocIdSrc']#.pack() #TODO
        data += pack('<L', 0x00020004)
        data += pack('<L', 0xabababab) # ALIGN
        data += self['usnvecFrom'].pack()
        if self['pUpToDateVecDest']:
            data += pack('<L', 0x00020008)
        else:
            data += pack('<L', 0)
        data += pack('<L', self['ulFlags'])
        data += pack('<L', self['cMaxObjects'])
        data += pack('<L', self['cMaxBytes'])
        data += pack('<L', self['ulExtendedOp'])
        data += pack('<L', 0xabababab) # ALIGN
        data += pack('<Q', self['liFsmoInfo'])
        if self['pPartialAttrSet']:
            data += pack('<L', 0x0002000c)
        else:
            data += pack('<L', 0)
        if self['pPartialAttrSetEx']:
            data += pack('<L', 0x00020010)
        else:
            data += pack('<L', 0)
        data += self['PrefixTableDest'].pack()
        data += self['pNC'].pack()

        # Mandatory padding!
        if len(data)%4:
            data += (4-len(data)%4)*'e'

        # TODO: Reverse the last part
        data += '08000000'.decode('hex')
        data += '01000000'.decode('hex')
        data += '00000000'.decode('hex')
        data += '08000000'.decode('hex')
        data += '5e000000'.decode('hex')
        data += '92000000'.decode('hex')
        data += '5a000000dd000000'.decode('hex')
        data += '7d000000a0000000'.decode('hex')
        data += '9002000037000000'.decode('hex')
        data += '0100000000000000'.decode('hex')
        data += '080000007b790000'.decode('hex')
        data += '080000002a864886'.decode('hex')
        data += 'f7140104'.decode('hex')
        return data


"""
4.1.10.2.11 DRS_MSG_GETCHGREPLY_V6
----------------------------------

typedef struct {
    UUID uuidDsaObjSrc;
    UUID uuidInvocIdSrc;
    [unique] DSNAME* pNC;
    USN_VECTOR usnvecFrom;
    USN_VECTOR usnvecTo;
    [unique] UPTODATE_VECTOR_V2_EXT* pUpToDateVecSrc;
    SCHEMA_PREFIX_TABLE PrefixTableSrc;
    ULONG ulExtendedRet;
    ULONG cNumObjects;
    ULONG cNumBytes;
    [unique] REPLENTINFLIST* pObjects;
    BOOL fMoreData;
    ULONG cNumNcSizeObjects;
    ULONG cNumNcSizeValues;
    [range(0,1048576)] DWORD cNumValues;
    [size_is(cNumValues)] REPLVALINF_V1* rgValues;
    DWORD dwDRSError;
} DRS_MSG_GETCHGREPLY_V6;
"""

class DrsMsgGetchgReplyV6(Struct):
    st = [
        ['uuidDsaObjSrc', '0s', ''],
        ['uuidInvocIdSrc', '0s', ''],
        ['pNC', '0s', ''],
        ['usnvecFrom', '0s', ''],
        ['usnvecTo', '0s', ''],
        ['pUpToDateVecSrc', '0s', ''],
        ['PrefixTableSrc', '0s', ''],
        ['ulExtendedRet', '<L', 0],
        ['cNumObjects', '<L', 0 ],
        ['cNumBytes', '<L', 0],
        ['pObjects', '0s', ''],
        ['fMoreData', '<L', 0],
        ['cNumNcSizeObjects', '<L', 0],
        ['cNumNcSizeValues', '<L', 0],
        ['cNumValues', '<L', 0],
        ['rgValues', '0s', ''],
        ['dwDRSError', '<L', 0],
    ]

    # Broken, simingly
    def __get_sid(x):
        return DCERPCSid(data=x[0]).get_sid()

    def __get_bool(x):
        return bool(unpack("<L", x[0])[0])

    def __get_u32(x):
        return unpack("<L", x[0])[0]

    def __get_buffer(x):
        return x[0].encode('hex')

    def __get_unicode_str(x):
        return x[0].decode('UTF-16LE')


    # http://www.kouti.com/tables/userattributes.htm
    UserAttributes = [
            { 'LDAPName':'instanceType',
              'Oid':'1.2.840.113556.1.2.1',
              'handler':__get_u32,
            },
            { 'LDAPName':'whenCreated',
              'Oid':'1.2.840.113556.1.2.2',
              'handler':None,
            },
            { 'LDAPName':'displayName',
              'Oid':'1.2.840.113556.1.2.13',
              'handler':None,
            },
            { 'LDAPName':'nTSecurityDescriptor',
              'Oid':'1.2.840.113556.1.2.281',
              'handler':__get_buffer,
            },
            { 'LDAPName':'name',
              'Oid':'1.2.840.113556.1.4.1',
              'handler':__get_unicode_str,
            },
            { 'LDAPName':'objectSid',
              'Oid':'1.2.840.113556.1.4.146',
              'handler':None,
            },
            { 'LDAPName':'primaryGroupID',
              'Oid':'1.2.840.113556.1.4.98',
              'handler':__get_u32,
            },
            { 'LDAPName':'userAccountControl',
              'Oid':'1.2.840.113556.1.4.8',
              'handler':__get_u32,
            },
            { 'LDAPName':'userPassword',
              'Oid':'2.5.4.35',
              'handler':None,
            },
            { 'LDAPName':'userPrincipalName',
              'Oid':'1.2.840.113556.1.4.656',
              'handler':None,
            },
            { 'LDAPName':'userSharedFolder',
              'Oid':'1.2.840.113556.1.4.751',
              'handler':None,
            },
            { 'LDAPName':'dBCSPwd',
              'Oid':'1.2.840.113556.1.4.55',
              'handler':__get_buffer,
            },
            { 'LDAPName':'cn',
              'Oid':'2.5.4.3',
              'handler':None,
            },
            { 'LDAPName':'description',
              'Oid':'2.5.4.13',
              'handler':__get_unicode_str,
            },
            { 'LDAPName':'objectCategory',
              'Oid':'1.2.840.113556.1.4.782',
              'handler':__get_buffer,
            },
            { 'LDAPName':'pwdLastSet',
              'Oid':'1.2.840.113556.1.4.96',
              'handler':None,
            },
            { 'LDAPName':'sAMAccountType',
              'Oid':'1.2.840.113556.1.4.302',
              'handler':None,
            },
            { 'LDAPName':'accountExpires',
              'Oid':'1.2.840.113556.1.4.159',
              'handler':None,
            },
            { 'LDAPName':'accountNameHistory',
              'Oid':'1.2.840.113556.1.4.1307',
              'handler':None,
            },
            { 'LDAPName':'objectClass',
              'Oid':'2.5.4.0',
              'handler':None,
            },
            { 'LDAPName':'countryCode',
              'Oid':'1.2.840.113556.1.4.25',
              'handler':__get_u32,
            },
            { 'LDAPName':'codePage',
              'Oid':'1.2.840.113556.1.4.16',
              'handler':__get_u32,
            },
            { 'LDAPName':'sAMAccountName',
              'Oid':'1.2.840.113556.1.4.221',
              'handler':__get_unicode_str,
            },
            { 'LDAPName':'unicodePwd',
              'Oid':'1.2.840.113556.1.4.90',
              'handler':__get_buffer,
            },
            { 'LDAPName':'isCriticalSystemObject',
              'Oid':'1.2.840.113556.1.4.868',
              'handler':__get_bool,
            },
            { 'LDAPName':'adminCount',
              'Oid':'1.2.840.113556.1.4.150',
              'handler':None,
            },
        ]

    def get_attribute_by_oid(self, oid):

        for attr in self.UserAttributes:
            if oid == attr['Oid']:
                return attr

    def get_attribute_by_name(self, name):

        user_attribute = None
        for elt in self.UserAttributes:
            if name == elt['LDAPName']:
                user_attribute = elt
                break
        if not user_attribute:
            return None

        for oid,data in self.attrs:
            if oid == user_attribute['Oid']:
                return data
        return None

    def dump_attributes(self):

        for x,y in self.attrs:
            attr = self.get_attribute_by_oid(x)
            if attr:
                if attr['handler']:
                    print "%s: \"%s\"" % (attr['LDAPName'], attr['handler'](y))
                else:
                    print "%s: (raw) \"%s\"" % (attr['LDAPName'], y)
            else:
                print "OID %s: (raw) \"%s\"" % (x, y)

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.attrs = []

        if data is not None:

            # DrsMsgGetchgReplyV6
            pos = 0
            tag = unpack('<L', data[pos:pos+4])[0] # v6
            pos += 4
            self['uuidDsaObjSrc'] = DCERPCGuid(data=data[pos:])
            pos += len(self['uuidDsaObjSrc'].pack())
            self['uuidInvocIdSrc'] = DCERPCGuid(data=data[pos:])
            pos += len(self['uuidInvocIdSrc'].pack())
            pNC = unpack('<L', data[pos:pos+4])[0] # pNC PTR
            pos += 8 # padding skipped (4 bytes)
            self['usnvecFrom'] = DrsUsnVector(data=data[pos:])
            pos += len(self['usnvecFrom'].pack())
            self['usnvecTo'] = DrsUsnVector(data=data[pos:])
            pos += len(self['usnvecTo'].pack())
            pUpToDateVecSrc = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['PrefixTableSrc'] = DrsSchemaPrefixTable(data=data[pos:])
            pos += len(self['PrefixTableSrc'].pack())
            self['ulExtendedRet'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cNumObjects'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cNumBytes'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            pObjects = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fMoreData'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cNumNcSizeObjects'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cNumNcSizeValues'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cNumValues'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            rgValues = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['dwDRSError'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            # Reply.pNC
            if pNC:
                self['pNC'] = DrsName(data=data[pos:])
                pos += self['pNC'].calcsize(padding=True)

            # Reply.PrefixTableSrc
            if not self['PrefixTableSrc'].is_empty():
                prefix_table = DrsPrefixTableEntryArray(data=data[pos:])
                pos += prefix_table.calcsize()

            # reply.pObjects
            if pObjects:
                Objects = DrsReplentInfList(data=data[pos:])
                pos += Objects.calcsize()

                # reply.pObjects.pName
                if Objects.has_name():
                    name_object = DrsName(data=data[pos:])
                    #print name_object['StringName'].encode('hex')
                    # TOTO: fix offset bug
                    pos += name_object.calcsize(padding=True)

            # reply.pObjects.Entinf.AttrBlock
            nbr_attributes = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            attr_objects = []

            for i in xrange(nbr_attributes):
                attr_object = DrsAttr(data=data[pos:])
                attr_objects.append(attr_object)
                pos += attr_object.calcsize()
            for idx in xrange(len(attr_objects)):
                nbr_values = attr_objects[idx].get_value().get_nbr_values()
                if not nbr_values:
                    continue
                values = DrsAttrValArray(data=data[pos:])
                pos += values.calcsize()

                # We save these attributes in an array
                oid = self.OidFromAttid(prefix_table, attr_objects[idx].get_type())
                val = []
                for elt in values.get_values():
                    val.append(elt['data'].get_raw())

                self.attrs.append((oid, val))

        else:
            pass
            # TODO

    # 5.16.4 ATTRTYP-to-OID Conversion
    def OidFromAttid(self, PrefixTable, attrtyp):
        """
        This helper function returns the OID
        """


        prefix_index = attrtyp >> 16
        sufix_value = attrtyp & 0xffff

        oid = PrefixTable.get_elements()[prefix_index].get_raw()[2:]
        if sufix_value < 128:
            oid += pack('B', sufix_value)
        else:
            if sufix_value >= 32768:
                sufix_value = sufix_value - 32768
            oid += pack('B', int((sufix_value /128) % 128 + 128))
            oid += pack('B', int(sufix_value % 128))

        return str(decoder.decode("\x06" + chr(len(oid)) + oid)[0])

    def pack(self):

        # TODO
        data = ''
        return data


"""
4.1.4.1.2 DRS_MSG_CRACKREQ_V1
-----------------------------
typedef struct {
    ULONG CodePage;
    ULONG LocaleId;
    DWORD dwFlags;
    DWORD formatOffered;
    DWORD formatDesired;
    [range(1,10000)] DWORD cNames;
    [string, size_is(cNames)] WCHAR** rpNames;
} DRS_MSG_CRACKREQ_V1;
"""

class DrsMsgCrackreqV1(Struct):
    st = [
        ['CodePage', '<L', 0],
        ['LocaleId', '<L', 0],
        ['dwFlags', '<L', 0],
        ['formatOffered', '<L', DS_SID_OR_SID_HISTORY_NAME],
        ['formatDesired', '<L', DS_FQDN_1779_NAME],
        ['cNames', '<L', 0],
        ['rpNames', '0s', ''],
    ]

    def __init__(self, data=None, names=[], in_format=DS_SID_OR_SID_HISTORY_NAME, out_format=DS_FQDN_1779_NAME, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['cNames'] = len(names)
            self['rpNames'] = names
            self['formatOffered'] = in_format
            self['formatDesired'] = out_format

    def pack(self):

        data  = pack('<L', 1) # V1
        data += Struct.pack(self)

        # The array
        data += pack('<L', 0x20004)
        data += pack('<L', len(self['rpNames']))
        for name in self['rpNames']:
            data += pack('<L', 0x20008)
            data += DCERPCString(string=name.encode('UTF-16LE')).pack()
        return data

"""
4.1.5.1.2 DRS_MSG_DCINFOREQ_V1
------------------------------

typedef struct {
    [string] WCHAR* Domain;
    DWORD InfoLevel;
} DRS_MSG_DCINFOREQ_V1;
"""

class DrsMsgDcInfoReqV1(Struct):
    st = [
        ['Domain', '0s', 0],
        ['InfoLevel', '<L', 1],
    ]

    def __init__(self, data=None, domain='', info_level=2, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
        else:
            self['Domain'] = DCERPCString(string=domain.encode('UTF-16LE'))
            self['InfoLevel'] = info_level

    def pack(self):

        data  = pack('<L', 1) # V1
        data += pack('<L', 0x20004)
        data += pack('<L', self['InfoLevel'])
        data += self['Domain'].pack()
        return data

"""
4.1.4.1.4 DS_NAME_RESULT_ITEMW
------------------------------
typedef struct {
    DWORD status;
    [string, unique] WCHAR* pDomain;
    [string, unique] WCHAR* pName;
} DS_NAME_RESULT_ITEMW,
*PDS_NAME_RESULT_ITEMW;
"""

class DrsNameResultItemw(Struct):
    st = [
        ['status', '<L', 0],
        ['pDomain', '0s', ''],
        ['pName', '0s', ''],
    ]

    def __init__(self, data=None, itemw={}, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['status'] = unpack('<L', data[pos:pos+4])[0]
            # If everything is alright, status is 0
            if self['status'] == DS_NAME_NO_ERROR:
                pos += 4
                ptr2 = unpack('<L', data[pos:pos+4])[0]
                pos += 4
                ptr3 = unpack('<L', data[pos:pos+4])[0]
                pos += 4
                self['pDomain'] = DCERPCString(data=data[pos:])
                pos += len(self['pDomain'].pack())
                self['pName'] = DCERPCString(data=data[pos:])
                pos += len(self['pName'].pack())
            # If there is no mapping for the specific option, there are no
            # strings no fetch
            elif self['status'] == DS_NAME_ERROR_NO_MAPPING:
                pos += 4
                ptr2 = unpack('<L', data[pos:pos+4])[0]
                pos += 4
                ptr3 = unpack('<L', data[pos:pos+4])[0]

        else:
            self['status'] = itemw['result']
            self['pDomain'] = itemw['domain']
            self['pName'] = itemw['distinguishe_name']

    def pack(self):

        data  = pack('<L', self['status'])
        if self['pDomain']:
            data += pack('<L', 0x20004)
        else:
            data += pack('<L', 0)
        if self['pName']:
            data += pack('<L', 0x20008)
        else:
            data += pack('<L', 0)
        if self['pDomain']:
            data += self['pDomain'].pack()
        if self['pName']:
            data += self['pName'].pack()
        return data

    def get_item(self):
        domain = self['pDomain']
        if domain:
            domain = domain.get_string().decode('UTF-16LE')[:-1]
        distinguishe_name = self['pName']
        if distinguishe_name:
            distinguishe_name = distinguishe_name.get_string().decode('UTF-16LE')[:-1]
        return {'result':self['status'],
                'domain':domain,
                'distinguishe_name':distinguishe_name}


"""
4.1.4.1.5 DS_NAME_RESULTW
typedef struct {
    DWORD cItems;
    [size_is(cItems)] PDS_NAME_RESULT_ITEMW rItems;
} DS_NAME_RESULTW,*PDS_NAME_RESULTW;
"""

class DrsNameResultw(Struct):
    st = [
        ['cItems', '<L', 0],
    ]

    def __init__(self, data=None, results=[], is_unicode=True):
        Struct.__init__(self, data)
        self.items = []

        if data is not None:

            pos = 0
            ptr0 = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            nbr_items = unpack('<L', data[pos:pos+4])[0] # nbr_items or version?
            pos += 4
            ptr1 = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cItems'] = unpack('<L', data[pos:pos+4])[0] # nbr_items?
            pos += 4

            for i in xrange(self['cItems']):

                itemw = DrsNameResultItemw(data=data[pos:])
                self.items.append(itemw)
                pos += len(itemw.pack())

        else:
            self['cItems'] = len(results)
            self.items = results

    def pack(self):

        data  = pack('<L', 0x20004)
        data += pack('<L', self['cItems'])
        data  = pack('<L', 0x20008)
        data += pack('<L', self['cItems'])
        for itemw in self.items:
            data += itemw.pack()
        return data

    def get_results(self):
        res = []
        for itemw in self.items:
            res.append(itemw.get_item())
        return res

# Warning:
# --------
#     + Only certified able to deal with 1 array element
#     + The parsing is reduced to the specific case:
#           formatOffered = DS_SID_OR_SID_HISTORY_NAME
#           formatDesired = DS_FQDN_1779_NAME
#

class DrsMsgCrackreplyV1(Struct):
    st = [
        ['pResult', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            version = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['pResult'] = DrsNameResultw(data=data[pos:])

        else:
            pass

    def pack(self):

        data  = pack('<L', 1)
        data += self['pResult'].pack()
        return data

    def get_results(self):
        return self['pResult'].get_results()


"""
4.1.5.1.9 DS_DOMAIN_CONTROLLER_INFO_2W
--------------------------------------

typedef struct {
    [string, unique] WCHAR* NetbiosName;
    [string, unique] WCHAR* DnsHostName;
    [string, unique] WCHAR* SiteName;
    [string, unique] WCHAR* SiteObjectName;
    [string, unique] WCHAR* ComputerObjectName;
    [string, unique] WCHAR* ServerObjectName;
    [string, unique] WCHAR* NtdsDsaObjectName;
    BOOL fIsPdc;
    BOOL fDsEnabled;
    BOOL fIsGc;
    GUID SiteObjectGuid;
    GUID ComputerObjectGuid;
    GUID ServerObjectGuid;
    GUID NtdsDsaObjectGuid;
} DS_DOMAIN_CONTROLLER_INFO_2W;
"""

class DrsDomainControllerInfo2W(Struct):
    st = [
        ['NetbiosName', '0s', ''],
        ['DnsHostName', '0s', ''],
        ['SiteName', '0s', ''],
        ['SiteObjectName', '0s', ''],
        ['ComputerObjectName', '0s', ''],
        ['ServerObjectName', '0s', ''],
        ['NtdsDsaObjectName', '0s', ''],
        ['fIsPdc', '<L', 0],
        ['fDsEnabled', '<L', 0],
        ['fIsGc', '<L', 0],
        ['SiteObjectGuid', '16s', '\x00'*16],
        ['ComputerObjectGuid', '16s', '\x00'*16],
        ['ServerObjectGuid', '16s', '\x00'*16],
        ['NtdsDsaObjectGuid', '16s', '\x00'*16],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.pNetbiosName = 0
        self.pDnsHostName = 0
        self.pSiteName = 0
        self.pSiteObjectName = 0
        self.pComputerObjectName = 0
        self.pServerObjectName = 0
        self.pNtdsDsaObjectName = 0
        self.results = {}

        if data is not None:
            pos = 0
            version = unpack('<L', data[pos:pos+4])[0]
            self.results['version'] = version
            pos += 4
            self.pNetbiosName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pDnsHostName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pSiteName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pSiteObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pComputerObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pServerObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pNtdsDsaObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fIsPdc'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fDsEnabled'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fIsGc'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['SiteObjectGuid'] = data[pos:pos+16]
            self.results['SiteObjectName'] = self['SiteObjectGuid']
            pos += 16
            self['ComputerObjectGuid'] = data[pos:pos+16]
            self.results['ComputerObjectGuid'] = self['ComputerObjectGuid']
            pos += 16
            self['ServerObjectGuid'] = data[pos:pos+16]
            self.results['ServerObjectGuid'] = self['ServerObjectGuid']
            pos += 16
            self['NtdsDsaObjectGuid'] = data[pos:pos+16]
            self.results['NtdsDsaObjectGuid'] = self['NtdsDsaObjectGuid']
            pos += 16
            if self.pNetbiosName:
                self['NetbiosName'] = DCERPCString(data=data[pos:])
                pos += len(self['NetbiosName'].pack())
                self.results['NetbiosName'] = self['NetbiosName'].get_string()
            if self.pDnsHostName:
                self['DnsHostName'] = DCERPCString(data=data[pos:])
                pos += len(self['DnsHostName'].pack())
                self.results['DnsHostName'] = self['DnsHostName'].get_string()
            if self.pSiteName:
                self['SiteName'] = DCERPCString(data=data[pos:])
                pos += len(self['SiteName'].pack())
                self.results['SiteName'] = self['SiteName'].get_string()
            if self.pSiteObjectName:
                self['SiteObjectName'] = DCERPCString(data=data[pos:])
                self.results['SiteObjectName'] = self['SiteObjectName'].get_string()
                pos += len(self['SiteObjectName'].pack())
            if self.pComputerObjectName:
                self['ComputerObjectName'] = DCERPCString(data=data[pos:])
                self.results['ComputerObjectName'] = self['ComputerObjectName'].get_string()
                pos += len(self['ComputerObjectName'].pack())
            if self.pServerObjectName:
                self['ServerObjectName'] = DCERPCString(data=data[pos:])
                self.results['ServerObjectName'] = self['ServerObjectName'].get_string()
                pos += len(self['ServerObjectName'].pack())
            if self.pNtdsDsaObjectName:
                self['NtdsDsaObjectName'] = DCERPCString(data=data[pos:])
                self.results['NtdsDsaObjectName'] = self['NtdsDsaObjectName'].get_string()
                pos += len(self['NtdsDsaObjectName'].pack())
        else:
            # TODO
            pass

    def pack(self):

        # TODO - Finish it with arguments
        data  = pack('<L', 1) # version
        data += pack('<L', self.pNetbiosName)
        data += pack('<L', self.pDnsHostName)
        data += pack('<L', self.pSiteName)
        data += pack('<L', self.pSiteObjectName)
        data += pack('<L', self.pComputerObjectName)
        data += pack('<L', self.pServerObjectName)
        data += pack('<L', self.pNtdsDsaObjectName)
        data += pack('<L', self['fIsPdc'])
        data += pack('<L', self['fDsEnabled'])
        data += pack('<L', self['fIsGc'])
        return data

    def get_results(self):
        return self.results


"""
4.1.5.1.8 DS_DOMAIN_CONTROLLER_INFO_1W
--------------------------------------

typedef struct {
    [string, unique] WCHAR* NetbiosName;
    [string, unique] WCHAR* DnsHostName;
    [string, unique] WCHAR* SiteName;
    [string, unique] WCHAR* ComputerObjectName;
    [string, unique] WCHAR* ServerObjectName;
    BOOL fIsPdc;
    BOOL fDsEnabled;
} DS_DOMAIN_CONTROLLER_INFO_1W;
"""

class DrsDomainControllerInfo1W(Struct):
    st = [
        ['NetbiosName', '0s', ''],
        ['DnsHostName', '0s', ''],
        ['SiteName', '0s', ''],
        ['ComputerObjectName', '0s', ''],
        ['ServerObjectName', '0s', ''],
        ['fIsPdc', '<L', 0],
        ['fDsEnabled', '<L', 0],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.pNetbiosName = 0
        self.pDnsHostName = 0
        self.pSiteName = 0
        self.pComputerObjectName = 0
        self.pServerObjectName = 0
        self.results = {}

        if data is not None:
            pos = 0
            version = unpack('<L', data[pos:pos+4])[0]
            self.results['version'] = version
            pos += 4
            self.pNetbiosName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pDnsHostName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pSiteName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pComputerObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.pServerObjectName = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fIsPdc'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['fDsEnabled'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            if self.pNetbiosName:
                self['NetbiosName'] = DCERPCString(data=data[pos:])
                self.results['NetbiosName'] = self['NetbiosName'].get_string()
                pos += len(self['NetbiosName'].pack())
            if self.pDnsHostName:
                self['DnsHostName'] = DCERPCString(data=data[pos:])
                self.results['DnsHostName'] = self['DnsHostName'].get_string()
                pos += len(self['DnsHostName'].pack())
            if self.pSiteName:
                self['SiteName'] = DCERPCString(data=data[pos:])
                self.results['SiteName'] = self['SiteName'].get_string()
                pos += len(self['SiteName'].pack())
            if self.pComputerObjectName:
                self['ComputerObjectName'] = DCERPCString(data=data[pos:])
                self.results['ComputerObjectName'] = self['ComputerObjectName'].get_string()
                pos += len(self['ComputerObjectName'].pack())
            if self.pServerObjectName:
                self['ServerObjectName'] = DCERPCString(data=data[pos:])
                self.results['ServerObjectName'] = self['ServerObjectName'].get_string()
                pos += len(self['ServerObjectName'].pack())
        else:
            # TODO
            pass

    def pack(self):

        # TODO - Finish it with arguments
        data  = pack('<L', 1) # version
        data += pack('<L', self.pNetbiosName)
        data += pack('<L', self.pDnsHostName)
        data += pack('<L', self.pSiteName)
        data += pack('<L', self.pComputerObjectName)
        data += pack('<L', self.pServerObjectName)
        data += pack('<L', self['fIsPdc'])
        data += pack('<L', self['fDsEnabled'])
        return data

    def get_results(self):
        return self.results


"""
4.1.5.1.4 DRS_MSG_DCINFOREPLY_V1
typedef struct {
    [range(0,10000)] DWORD cItems;
    [size_is(cItems)] DS_DOMAIN_CONTROLLER_INFO_1W* rItems;
} DRS_MSG_DCINFOREPLY_V1;
"""

class DrsMsgDcinforeplyV1(Struct):
    st = [
        ['cItems', '0s', ''],
        ['rItems', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.prItems = 0

        if data is not None:
            pos = 0
            version = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cItems'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.prItems = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            if self.prItems:
                self['rItems'] = DrsDomainControllerInfo1W(data=data[pos:])
        else:
            # TODO
            pass

    def pack(self):

        data  = pack('<L', 1)
        data += pack('<L', self['cItems'])
        if self['rItems']:
            data += pack('<L', 0x2000c)
            data += self['rItems'].pack()
        else:
            data += pack('<L', 0)
        return data

    def get_results(self):
        return self['rItems'].get_results()

"""
typedef struct {
    [range(0,10000)] DWORD cItems;
    [size_is(cItems)] DS_DOMAIN_CONTROLLER_INFO_2W* rItems;
} DRS_MSG_DCINFOREPLY_V2;
"""

class DrsMsgDcinforeplyV2(Struct):
    st = [
        ['cItems', '0s', ''],
        ['rItems', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)
        self.prItems = 0

        if data is not None:
            pos = 0
            version = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['cItems'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self.prItems = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            if self.prItems:
                self['rItems'] = DrsDomainControllerInfo2W(data=data[pos:])
        else:
            # TODO
            pass

    def pack(self):

        data  = pack('<L', 2)
        data += pack('<L', self['cItems'])
        if self['rItems']:
            data += pack('<L', 0x2000c)
            data += self['rItems'].pack()
        else:
            data += pack('<L', 0)
        return data

    def get_results(self):
        return self['rItems'].get_results()

###
# Handlers
# No exception handling for these objects.
###

# Opnum 0

'''
ULONG IDL_DRSBind(
    [in] handle_t rpc_handle,
    [in, unique] UUID* puuidClientDsa,
    [in, unique] DRS_EXTENSIONS* pextClient,
    [out] DRS_EXTENSIONS** ppextServer,
    [out, ref] DRS_HANDLE* phDrs
);
'''

class NetrDsBindRequest(Struct):
    st = [
        ['puuidClientDsa', '0s', ''],
        ['pextClient', '0s', ''],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            ### TODO
        else:
            self['puuidClientDsa'] = DCERPCGuid(guid=NTDSAPI_CLIENT_GUID)
            self['pextClient'] = DrsExtensions(drs_entensions=DrsExtensionsInt())

    def pack(self):

        data  = pack('<L', 0x20004)
        data += self['puuidClientDsa'].pack()
        data += pack('<L', 0x20008)
        data += self['pextClient'].pack()
        return data

class NetrDsBindResponse(Struct):
    st = [
        ['RefPtr', '<L', 0x20004],
        ['cb', '<L', 0x1c],
        ['Extensions', '0s', ''],
        ['Handle', '20s', '\x00'*20],
    ]

    def __init__(self, data=None, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 8
            cb = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['Extensions'] = data[pos:pos+cb]
            pos += len(self['Extensions'])
            self['Handle'] = DrsHandle(data=data[pos:])
        else:
            pass
            ## TODO

    def pack(self):
        data  = pack('<L', 0x20004)
        data += pack('<L', self['cb'])
        data += pack('<L', self['cb'])
        data += self['Extensions']
        data += self['Handle'].pack()
        return data

    def get_handle(self):
        return self['Handle'].pack()

# Opnum 3

"""
ULONG IDL_DRSGetNCChanges(
    [in, ref] DRS_HANDLE hDrs,
    [in] DWORD dwInVersion,
    [in, ref, switch_is(dwInVersion)]
    DRS_MSG_GETCHGREQ* pmsgIn,
    [out, ref] DWORD* pdwOutVersion,
    [out, ref, switch_is(*pdwOutVersion)]
    DRS_MSG_GETCHGREPLY* pmsgOut
);
"""

class NetrDsGetNCChangesRequest(Struct):
    st = [
        ['hDrs', '0s', ''],
        ['dwInVersion', '<L', 8],
        ['pmsgIn', '0s', ''],
    ]

    def __init__(self, data=None, handle='', version=8, username='', NtdsDsaObjectGuid='', is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            ### TODO
        else:
            self['hDrs'] = DrsHandle(data=handle)
            self['dwInVersion'] = version
            if version == 8:
                self['pmsgIn'] = DrsMsgGetchgreqV8(username=username, NtdsDsaObjectGuid=NtdsDsaObjectGuid)
            else:
                self['pmsgIn'] = ''

    def pack(self):

        data  = self['hDrs'].pack()
        data += pack('<L', self['dwInVersion'])
        if self['pmsgIn']:
            data += self['pmsgIn'].pack()
        return data

"""
4.1.10.2.8 DRS_MSG_GETCHGREPLY
------------------------------

typedef
[switch_type(DWORD)]
union {
     [case(1)]
    DRS_MSG_GETCHGREPLY_V1
    [case(2)]
    DRS_MSG_GETCHGREPLY_V2
    [case(6)]
    DRS_MSG_GETCHGREPLY_V6
    [case(7)]
    DRS_MSG_GETCHGREPLY_V7
    [case(9)]
    DRS_MSG_GETCHGREPLY_V9
} DRS_MSG_GETCHGREPLY;
"""

class NetrDsGetNCChangesResponse(Struct):
    st = [
        ['dwOutVersion', '<L', 6],
        ['pmsgOut', '0s', ''],
        ['retvalue', '<L', 0],
    ]

    def __init__(self, data=None, version=6, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['dwOutVersion'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            if self['dwOutVersion'] == 6:
                pmsgOut = DrsMsgGetchgReplyV6(data=data[pos:])
                self['pmsgOut'] = pmsgOut
                pos += len(pmsgOut.pack())
            else:
                self['pmsgOut'] = ''
            self['retvalue'] = unpack('<L', data[pos:pos+4])[0]
        else:
            self['dwOutVersion'] = version
            if version == 6:
                self['pmsgOut'] = DrsMsgGetchgReplyV6(username=username)
            else:
                self['pmsgIn'] = ''

    def pack(self):

        data += pack('<L', self['dwOutVersion'])
        if self['pmsgOut']:
            data += self['pmsgOut'].pack()
        data += pack('<L', self['retvalue'])
        return data

    def get_results(self):
        dic = {}
        dic['encrypted_LM'] = self['pmsgOut'].get_attribute_by_name('dBCSPwd')
        dic['encrypted_NTLM'] = self['pmsgOut'].get_attribute_by_name('unicodePwd')
        return dic

# Opnum 12

"""
ULONG IDL_DRSCrackNames(
    [in, ref] DRS_HANDLE hDrs,
    [in] DWORD dwInVersion,
    [in, ref, switch_is(dwInVersion)]
    DRS_MSG_CRACKREQ* pmsgIn,
    [out, ref] DWORD* pdwOutVersion,
    [out, ref, switch_is(*pdwOutVersion)]
    DRS_MSG_CRACKREPLY* pmsgOut
);
"""

class NetrDsCrackNamesRequest(Struct):
    st = [
        ['hDrs', '0s', ''],
        ['dwInVersion', '<L', 1],
        ['pmsgIn', '0s', ''],
    ]

    def __init__(self, data=None, handle='', names=[], in_format=DS_SID_OR_SID_HISTORY_NAME, out_format=DS_FQDN_1779_NAME, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            ### TODO
        else:
            self['hDrs'] = DrsHandle(data=handle)
            self['pmsgIn'] = DrsMsgCrackreqV1(names=names, in_format=in_format, out_format=out_format)

    def pack(self):

        data  = self['hDrs'].pack()
        data += pack('<L', self['dwInVersion'])
        data += self['pmsgIn'].pack()
        return data

"""
4.1.4.1.6 DRS_MSG_CRACKREPLY
----------------------------

typedef
[switch_type(DWORD)]
union {
    [case(1)]
    DRS_MSG_CRACKREPLY_V1 V1;
} DRS_MSG_CRACKREPLY;
"""

class NetrDsCrackNamesResponse(Struct):
    st = [
        ['dwOutVersion', '<L', 1],
        ['pmsgOut', '0s', ''],
        ['retvalue', '<L', 0 ],
    ]

    def __init__(self, data=None, ret=0, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['dwOutVersion'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            self['pmsgOut'] = DrsMsgCrackreplyV1(data=data[pos:])
        else:
            self['retvalue'] = ret
            self['pmsgOut'] = DrsMsgCrackreplyV1()

    def pack(self):

        data  = pack('<L', self['dwOutVersion'])
        data += self['pmsgOut'].pack()
        data += pack('<L', self['retvalue'])
        return data

    def get_results(self):
        return self['pmsgOut'].get_results()

# Opnum 16

"""
ULONG IDL_DRSDomainControllerInfo(
    [in, ref] DRS_HANDLE hDrs,
    [in] DWORD dwInVersion,
    [in, ref, switch_is(dwInVersion)]
    DRS_MSG_DCINFOREQ* pmsgIn,
    [out, ref] DWORD* pdwOutVersion,
    [out, ref, switch_is(*pdwOutVersion)]
    DRS_MSG_DCINFOREPLY* pmsgOut
);
"""

class NetrDsGetDomainControllerInfoRequest(Struct):
    st = [
        ['hDrs', '0s', ''],
        ['dwInVersion', '<L', 1],
        ['pmsgIn', '0s', ''],
    ]

    def __init__(self, data=None, handle='', domain='', is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pass
            ### TODO
        else:
            self['hDrs'] = DrsHandle(data=handle)
            self['pmsgIn'] = DrsMsgDcInfoReqV1(domain=domain)

    def pack(self):

        data  = self['hDrs'].pack()
        data += pack('<L', self['dwInVersion'])
        data += self['pmsgIn'].pack()
        return data

"""
4.1.5.1.3 DRS_MSG_DCINFOREPLY
-----------------------------

typedef
[switch_type(DWORD)]
union {
    [case(1)]
    DRS_MSG_DCINFOREPLY_V1 V1;
    [case(2)]
    DRS_MSG_DCINFOREPLY_V2 V2;
    [case(3)]
    DRS_MSG_DCINFOREPLY_V3 V3;
    [case(0xFFFFFFFF)]
    DRS_MSG_DCINFOREPLY_VFFFFFFFF VFFFFFFFF;
} DRS_MSG_DCINFOREPLY;
"""

class NetrDsMsgDcInfoReplyResponse(Struct):
    st = [
        ['dwOutVersion', '<L', 1],
        ['pmsgOut', '0s', ''],
        ['retvalue', '<L', 0 ],
    ]

    def __init__(self, data=None, ret=0, is_unicode=True):
        Struct.__init__(self, data)

        if data is not None:
            pos = 0
            self['dwOutVersion'] = unpack('<L', data[pos:pos+4])[0]
            pos += 4
            if self['dwOutVersion'] == 1:
                self['pmsgOut'] = DrsMsgDcinforeplyV1(data=data[pos:])
            elif self['dwOutVersion'] == 2:
                self['pmsgOut'] = DrsMsgDcinforeplyV2(data=data[pos:])
            else:
                self['pmsgOut'] = None
        else:
            pass
            # TODO

    def pack(self):

        data  = pack('<L', self['dwOutVersion'])
        if not self['pmsgOut']:
            data += pack('<L', 0)
        else:
            data += self['pmsgOut'].pack()
        data += pack('<L', self['retvalue'])
        return data

    def get_results(self):
        return self['pmsgOut'].get_results()

#######################################################################
#####
##### Exception classes
#####
#######################################################################

class DRSUAPIException(Exception):
    """
    Base class for all DRSUAPI-specific exceptions.
    """
    def __init__(self, message=''):
        self.message = message

    def __str__(self):
        return '[ DRSUAPI_ERROR: %s ]' % (self.message)

class DRSUAPIException2(Exception):
    """
    Improved version of the base class to track errors.
    """
    def __init__(self, message='', status=None):
        self.message = message
        self.status = status

    def __str__(self):
        if not self.status:
            return '[ DRSUAPI_ERROR: %s ]' % (self.message)
        else:
            return '[ DRSUAPI_ERROR: %s (0x%x) ]' % (self.message, self.status)

class DRSUAPIBindException(DRSUAPIException2):
    """
    Raised when bind fails.
    """
    pass

class DRSUAPICrackNamesException(DRSUAPIException2):
    """
    Raised when crack_names fails.
    """
    pass

class DRSUAPIGetNCChangesException(DRSUAPIException2):
    """
    Raised when get_nc_changes fails.
    """
    pass

class DRSUAPIGetDomainControllerInfoException(DRSUAPIException2):
    """
    Raised when get_domain_controller_info fails.
    """
    pass

#######################################################################
#####
##### Main classes: DRSUAPI, DRSUAPIClient
##### API will raise specific exceptions when errors are caught.
#######################################################################

class DRSUAPI():
    def __init__(self, host, port):
        self.host              = host
        self.port              = port
        self.is_unicode        = True
        self.policy_handle     = None
        self.uuid              = (u'e3514235-4b06-11d1-ab04-00c04fc2dcd2', u'4.0')

class DRSUAPIClient(DRSUAPI):

    def __init__(self, host, port=135):
        DRSUAPI.__init__(self, host, port)
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

            return self.dce.bind(self.uuid[0], self.uuid[1], RPC_C_AUTHN_WINNT, RPC_C_AUTHN_LEVEL_PKT_PRIVACY)
        except Exception as e:
            #print e
            return 0

    def __bind_ntlm(self, connector):
        try:
            self.dce = DCERPC(connector,
                              getsock=None,
                              username=self.username,
                              password=self.password,
                              domain=self.domain)

            return self.dce.bind(self.uuid[0], self.uuid[1], RPC_C_AUTHN_WINNT, RPC_C_AUTHN_LEVEL_PKT_PRIVACY)
        except Exception as e:
            #print e
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

        epm = EPTClient(self.host)
        epm.set_credentials(username=self.username, password=self.password, domain=self.domain)
        # Could we bind?
        res = epm.bind()
        if not res:
            return 0

        entries = epm.ept_lookup()
        results = epm.convert_entries(entries)

        for res in results:
            # The uuid is in 'raw' form (same as self.uuid[0])
            if res['uuid'] == '5BQ\xe3\x06K\xd1\x11\xab\x04\x00\xc0O\xc2\xdc\xd2':
                if res.has_key('tcp'):
                    connector = u'ncacn_ip_tcp:%s[%d]' % (res['ip'],res['tcp'])
                    ret = self.__bind(connector)
                    if ret:
                        return 1
        return 0


    def get_reply(self):
        """
        Returns the reply packet
        """
        return self.dce.reassembled_data

    def __recover_hash(self, ciphertext, rpc_session_key, rid):
        """
        TODO.
        """

        salt = ciphertext[:16]
        initial_hash = ciphertext[16:]
        md5 = hashlib.new('md5')
        md5.update(rpc_session_key)
        md5.update(salt)
        computed_key = md5.digest()
        cipher = ARC4.new(computed_key)
        intermediate_hash = cipher.decrypt(initial_hash)[4:]
        Key1,Key2 = DeriveKeyFromLittleEndian(rid)
        Crypt1 = DES.des(Key1, mode=DES.ECB)
        Crypt2 = DES.des(Key2, mode=DES.ECB)
        final_hash  = Crypt1.decrypt(intermediate_hash[:8])
        final_hash += Crypt2.decrypt(intermediate_hash[8:])
        return final_hash

    def __get_session_key(self):
        """
        Returns the underlying session key.
        TODO: Kerberos session key should be handled too.
        """
        return  self.dce.ntlm.ExportedSessionKey

    def ds_bind(self):
        """
        Performs an application level binding (!= rpc binding).
        This provides you a handle that will be used for most of the operations.
        """

        try:
            data = NetrDsBindRequest().pack()
        except Exception as e:
            raise DRSUAPIBindException('ds_bind() failed to build the request.')

        self.dce.call(DRSUPAI_COM_DS_BIND, data, response=True)

        if len(self.get_reply()) < 4:
            raise DRSUAPIBindException('NetrDsBind() call was not correct.')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:
                resp = NetrDsBindResponse(data=self.get_reply())
                self.handle = resp.get_handle()
                return self.handle
            except Exception as e:
                raise DRSUAPIBindException('ds_bind() failed: Parsing error in the answer.')
        else:
            raise DRSUAPIBindException('NetrDsBind() failed.', status=status)


    def ds_crack_names(self, names=[]):
        """
        Transforms an AD account name.
        The API requires:
            a) The name you need to translate
            b) The input format (how did you provide it?)
            c) The output format (how do you expect it?)
        Currently we only handle SIDs.
        """

        try:
            data = NetrDsCrackNamesRequest(handle=self.handle, names=names).pack()
        except Exception as e:
            raise DRSUAPICrackNamesException('ds_crack_names() failed to build the request.')

        self.dce.call(DRSUPAI_COM_DS_CRACK_NAMES, data, response=True)
        #print self.get_reply().encode('hex')

        if len(self.get_reply()) < 4:
            raise DRSUAPICrackNamesException('NetrDsCrackNames() call was not correct.')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:
                resp = NetrDsCrackNamesResponse(data=self.get_reply())
                return resp.get_results()
            except Exception as e:
                raise DRSUAPICrackNamesException('ds_crack_names() failed: Parsing error in the answer.')
        else:
            raise DRSUAPICrackNamesException('NetrDsCrackNames() failed.', status=status)


    def ds_get_nc_changes(self, handle=None, NtdsDsaObjectGuid='', username='', rid=500):
        """
        Returns account information for a specific user.
        Note: the username must be using a specific format.
        """

        try:
            if not handle:
                handle = self.handle
            data = NetrDsGetNCChangesRequest(handle=handle, username=username, NtdsDsaObjectGuid=NtdsDsaObjectGuid).pack()
        except Exception as e:
            raise DRSUAPIGetNCChangesException('ds_get_nc_changes() failed to build the request.')

        #print "NetrDsGetNCChangesRequest [%d bytes]" % len(data.encode('hex')), data.encode('hex')
        self.dce.call(DRSUPAI_COM_DS_GET_NC_CHANGES, data, response=True)

        if len(self.get_reply()) < 4:
            raise DRSUAPIGetNCChangesException('NetrDsGetNcChanges() call was not correct.')

        data=self.get_reply()
        #print "NetrDsGetNCChangesResponse [%d bytes]" % len(data.encode('hex')), data.encode('hex')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:

                resp = NetrDsGetNCChangesResponse(data=self.get_reply())
                res = resp.get_results()
                rpc_session_key = self.__get_session_key()
                if res['encrypted_LM']:
                    enc_lm = res['encrypted_LM'][0]
                    h1 = self.__recover_hash(enc_lm, rpc_session_key, rid)
                    res['decrypted_LM'] = h1
                else:
                    h1 = ''
                    res['decrypted_LM'] = None
                if res['encrypted_NTLM']:
                    enc_ntlm = res['encrypted_NTLM'][0]
                    h2 = self.__recover_hash(enc_ntlm, rpc_session_key, rid)
                    res['decrypted_NTLM'] = h2
                else:
                    h2 = ''
                    res['decrypted_NTLM'] = None
                return res

            except Exception as e:
                raise DRSUAPIGetNCChangesException('get_nc_changes() failed: Parsing error in the answer.')
        else:
            raise DRSUAPIGetNCChangesException('NetrDsGetNcChanges() failed.', status=status)


    def ds_get_domain_controller_info(self, handle=None, domain=''):
        """
        Provides informations on the targeted domain.
        One mandatory one is the GUID of the DC.
        """

        try:
            if not handle:
                handle = self.handle
            data = NetrDsGetDomainControllerInfoRequest(handle=handle, domain=domain).pack()
        except Exception as e:
            raise DRSUAPIGetDomainControllerInfoException('ds_get_domain_controller_info() failed to build the request.')

        #print "NetrDsGetDomainControllerInfoRequest [%d bytes]" % len(data.encode('hex')), data.encode('hex')
        self.dce.call(DRSUPAI_COM_DS_GET_DOMAIN_CONTROLLER_INFO, data, response=True)

        if len(self.get_reply()) < 4:
            raise DRSUAPIGetDomainControllerInfoException('NetrDsGetDomainControllerInfo() call was not correct.')

        data=self.get_reply()
        #print "NetrDsGetDomainControllerInfoResponse [%d bytes]" % len(data.encode('hex')), data.encode('hex')

        status = unpack('<L', self.get_reply()[-4:])[0]
        if status == 0:
            try:
                resp = NetrDsMsgDcInfoReplyResponse(data=self.get_reply())
                return resp.get_results()
            except Exception as e:
                raise DRSUAPIGetDomainControllerInfoException('ds_get_domain_controller_info() failed: Parsing error in the answer.')
        else:
            raise DRSUAPIGetDomainControllerInfoException('NetrDsGetDomainControllerInfo() failed.', status=status)


#######################################################################
#####
##### A couple of useful functions for other parts of CANVAS
#####
#######################################################################

# TODO: kerberos
def drs_get_hashes(ad_ip, sids, username, password, domain, use_krb5=False, kerberos_db=None):

    drs = DRSUAPIClient(ad_ip)
    drs.set_credentials(username,
                        password,
                        domain,
                        use_krb5=use_krb5,
                        kerberos_db=kerberos_db)
    ret = drs.bind()
    if not ret:
        return 0, 'Authentication failed'

    drs.ds_bind()
    infos_domain = drs.ds_get_domain_controller_info(domain=domain)
    NtdsDsaObjectGuid = infos_domain['NtdsDsaObjectGuid']
    results = []
    for sid in sids:
        # First we need to fetch the name of the user
        names = drs.ds_crack_names(names=[sid])
        target_user = names[0]['distinguishe_name']
        try:
            rid = int(sid.split('-')[-1])
            res = drs.ds_get_nc_changes(NtdsDsaObjectGuid=NtdsDsaObjectGuid,
                                            username=target_user,
                                            rid=rid)
            results.append( (target_user, res['decrypted_LM'], res['decrypted_NTLM']) )
        except Exception, e:
            return 0, e
    return 1, results

#######################################################################
#####
##### Well, the main :D
#####
#######################################################################

# 2003 AD

#SID    = 'S-1-5-21-3059505291-2698340665-4262259236-%d'
#DC_IP  = '192.168.0.1'
#USER   = 'administrator'
#PASSWD = 'barbar123!'
#DOMAIN = 'IMMU2.COM'

# 2008 AD

SID    = 'S-1-5-21-2638583726-4241359654-2861412549-%d'
DC_IP  = '10.0.0.1'
USER   = 'administrator'
PASSWD = 'foobar123!'
DOMAIN = 'immu5.lab'

def test1():

    print "==== TEST 1 ===="
    drs = DRSUAPIClient(DC_IP)
    drs.set_credentials(USER, PASSWD, DOMAIN, use_krb5=False)
    ret = drs.bind()
    if not ret:
        print "bind failed!"
        return

    drs.ds_bind()
    infos_domain = drs.ds_get_domain_controller_info(domain=DOMAIN)
    NtdsDsaObjectGuid = infos_domain['NtdsDsaObjectGuid']

    sid = SID % 500
    print "SID: ", sid
    names = drs.ds_crack_names(names=[sid])
    print "NAME: %s" % names[0]['distinguishe_name']
    try:
        changes = drs.ds_get_nc_changes(NtdsDsaObjectGuid=NtdsDsaObjectGuid,
                                        username=names[0]['distinguishe_name'],
                                        rid=500)
        print "NTLM: %s" % changes['decrypted_NTLM'].encode('hex')
    except Exception, e:
        print e

def test2():

    print "==== TEST 2 ===="
    status, res = drs_get_hashes(DC_IP, [SID%500], USER, PASSWD, DOMAIN)
    if not status:
        print "Error:", str(res)
    else:
        print "RID 500: LM = %s, NTLM = %s" % (res[0][1].encode('hex'), res[0][2].encode('hex'))

if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == '-v':
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

    test1()
    test2()

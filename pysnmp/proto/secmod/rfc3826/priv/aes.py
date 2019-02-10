#
# This file is part of pysnmp software.
#
# Copyright (c) 2005-2019, Ilya Etingof <etingof@gmail.com>
# License: http://snmplabs.com/pysnmp/license.html
#
import random

try:
    from hashlib import md5, sha1

except ImportError:
    import md5
    import sha

    md5 = md5.new
    sha1 = sha.new

try:
    from pysnmpcrypto import aes, PysnmpCryptoError

except ImportError:
    PysnmpCryptoError = AttributeError
    aes = None

from pyasn1.type import univ
from pysnmp.proto.secmod.rfc3414.priv import base
from pysnmp.proto.secmod.rfc3414.auth import hmacmd5, hmacsha
from pysnmp.proto.secmod.rfc7860.auth import hmacsha2
from pysnmp.proto.secmod.rfc3414 import localkey
from pysnmp.proto import errind, error

random.seed()


# RFC3826

#

class Aes(base.AbstractEncryptionService):
    SERVICE_ID = (1, 3, 6, 1, 6, 3, 10, 1, 2, 4)  # usmAesCfb128Protocol
    KEY_SIZE = 16

    local_int = random.randrange(0, 0xffffffffffffffff)

    # 3.1.2.1
    def __getEncryptionKey(self, privKey, snmpEngineBoots, snmpEngineTime):
        salt = [self.local_int >> 56 & 0xff,
                self.local_int >> 48 & 0xff,
                self.local_int >> 40 & 0xff,
                self.local_int >> 32 & 0xff,
                self.local_int >> 24 & 0xff,
                self.local_int >> 16 & 0xff,
                self.local_int >> 8 & 0xff,
                self.local_int & 0xff]

        if self.local_int == 0xffffffffffffffff:
            self.local_int = 0
        else:
            self.local_int += 1

        return self.__getDecryptionKey(privKey, snmpEngineBoots, snmpEngineTime, salt) + (
        univ.OctetString(salt).asOctets(),)

    def __getDecryptionKey(self, privKey, snmpEngineBoots,
                           snmpEngineTime, salt):
        snmpEngineBoots, snmpEngineTime, salt = (
            int(snmpEngineBoots), int(snmpEngineTime), salt
        )

        iv = [snmpEngineBoots >> 24 & 0xff,
              snmpEngineBoots >> 16 & 0xff,
              snmpEngineBoots >> 8 & 0xff,
              snmpEngineBoots & 0xff,
              snmpEngineTime >> 24 & 0xff,
              snmpEngineTime >> 16 & 0xff,
              snmpEngineTime >> 8 & 0xff,
              snmpEngineTime & 0xff] + salt

        return privKey[:self.KEY_SIZE].asOctets(), univ.OctetString(iv).asOctets()

    def hashPassphrase(self, authProtocol, privKey):
        if authProtocol == hmacmd5.HmacMd5.SERVICE_ID:
            hashAlgo = md5
        elif authProtocol == hmacsha.HmacSha.SERVICE_ID:
            hashAlgo = sha1
        elif authProtocol in hmacsha2.HmacSha2.HASH_ALGORITHM:
            hashAlgo = hmacsha2.HmacSha2.HASH_ALGORITHM[authProtocol]
        else:
            raise error.ProtocolError(
                'Unknown auth protocol %s' % (authProtocol,)
            )
        return localkey.hashPassphrase(privKey, hashAlgo)

    def localizeKey(self, authProtocol, privKey, snmpEngineID):
        if authProtocol == hmacmd5.HmacMd5.SERVICE_ID:
            hashAlgo = md5
        elif authProtocol == hmacsha.HmacSha.SERVICE_ID:
            hashAlgo = sha1
        elif authProtocol in hmacsha2.HmacSha2.HASH_ALGORITHM:
            hashAlgo = hmacsha2.HmacSha2.HASH_ALGORITHM[authProtocol]
        else:
            raise error.ProtocolError(
                'Unknown auth protocol %s' % (authProtocol,)
            )
        localPrivKey = localkey.localizeKey(privKey, snmpEngineID, hashAlgo)
        return localPrivKey[:self.KEY_SIZE]

    # 3.2.4.1
    def encryptData(self, encryptKey, privParameters, dataToEncrypt):
        snmpEngineBoots, snmpEngineTime, salt = privParameters

        # 3.3.1.1
        aesKey, iv, salt = self.__getEncryptionKey(
            encryptKey, snmpEngineBoots, snmpEngineTime
        )

        # 3.3.1.3
        # PyCrypto seems to require padding
        dataToEncrypt = dataToEncrypt + univ.OctetString((0,) * (16 - len(dataToEncrypt) % 16)).asOctets()

        try:
            ciphertext = aes.encrypt(dataToEncrypt, aesKey, iv)

        except PysnmpCryptoError:
            raise error.StatusInformation(
                errorIndication=errind.unsupportedPrivProtocol
            )

        # 3.3.1.4
        return univ.OctetString(ciphertext), univ.OctetString(salt)

    # 3.2.4.2
    def decryptData(self, decryptKey, privParameters, encryptedData):
        snmpEngineBoots, snmpEngineTime, salt = privParameters

        # 3.3.2.1
        if len(salt) != 8:
            raise error.StatusInformation(
                errorIndication=errind.decryptionError
            )

        # 3.3.2.3
        aesKey, iv = self.__getDecryptionKey(
            decryptKey, snmpEngineBoots, snmpEngineTime, salt
        )

        # PyCrypto seems to require padding
        encryptedData = encryptedData + univ.OctetString((0,) * (16 - len(encryptedData) % 16)).asOctets()

        try:
            # 3.3.2.4-6
            return aes.decrypt(encryptedData.asOctets(), aesKey, iv)

        except PysnmpCryptoError:
            raise error.StatusInformation(
                errorIndication=errind.unsupportedPrivProtocol
            )

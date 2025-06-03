from cryptography.fernet import Fernet
import os
from ..core.config import logger
import base64

class EncryptionUtil:
    def __init__(self):
        key = os.environ.get('ENCRYPTION_KEY')
        if not key:
            logger.warning("ENCRYPTION_KEY not set, generating a new key for this session")
            return
        else:
            # Ensure the key is valid base64 and decodes to 32 bytes
            try:
                key_bytes = base64.urlsafe_b64decode(key)
                if len(key_bytes) != 32:
                    logger.warning(f"ENCRYPTION_KEY does not decode to 32 bytes (got {len(key_bytes)} bytes), generating a new key")
                    key = Fernet.generate_key().decode()
            except Exception as e:
                logger.error(f"Error processing ENCRYPTION_KEY: {e}")
                key = Fernet.generate_key().decode()
        self.cipher_suite = Fernet(key.encode())
        logger.info("Encryption utility initialized")

    def encrypt(self, data: str) -> str:
        """Encrypt a string."""
        if not data:
            return data
        assert isinstance(data, str), "Data to encrypt must be a string"
        return self.cipher_suite.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string."""
        if not encrypted_data:
            return encrypted_data
        assert isinstance(encrypted_data, str), "Data to decrypt must be a string"
        try:
            return self.cipher_suite.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")

# Singleton instance
encryption_util = EncryptionUtil() 
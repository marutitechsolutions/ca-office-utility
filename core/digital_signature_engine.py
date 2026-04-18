import os
import datetime
from utils.cert_utils import extract_common_name
# from endesive import pdf (removed in favor of pyhanko)
import win32crypt
import win32api
import pywintypes
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields
from pyhanko.sign.signers import PdfSignatureMetadata, sign_pdf, SimpleSigner
from pyhanko.pdf_utils.content import PdfContent

# Exhaustive search for TextParameters across different pyhanko versions
TextParameters = None
try:
    from pyhanko.pdf_utils.content import TextParameters as TP
    TextParameters = TP
except ImportError:
    try:
        from pyhanko.sign.general import TextParameters as TP
        TextParameters = TP
    except ImportError:
        try:
            from pyhanko.pdf_utils.layout import TextParameters as TP
            TextParameters = TP
        except ImportError:
            try:
                from pyhanko.sign.signers import TextParameters as TP
                TextParameters = TP
            except ImportError:
                print("WARNING: TextParameters not found in any known pyhanko location.")

try:
    from pyhanko.sign.signers.ms_crypto import MSCryptoSigner
except ImportError:
    try:
        from pyhanko.sign.signers.mscrypto import MSCryptoSigner
    except ImportError:
        try:
            from pyhanko.sign.signers.mscapi import MSCryptoSigner
        except ImportError:
            # Fallback implementation for frozen .exe environment
            from pyhanko.sign.signers.pdf_cms import Signer
            from asn1crypto import x509 as asn1_x509
            from asn1crypto import cms

            class MSCryptoSigner(Signer):
                def __init__(self, thumbprint, **kwargs):
                    self.thumbprint = thumbprint
                    self.store = None
                    self.cert_context = self._find_cert(thumbprint)
                    if not self.cert_context:
                        raise Exception(f"Certificate {thumbprint} not found.")
                    cert_bytes = self.cert_context.CertEncoded
                    signing_cert = asn1_x509.Certificate.load(cert_bytes)
                    super().__init__(signing_cert=signing_cert, **kwargs)

                def _find_cert(self, thumbprint):
                    import pythoncom
                    pythoncom.CoInitialize()
                    self.store = win32crypt.CertOpenStore(10, 0, None, 0x00010000, "MY")
                    for cert in self.store.CertEnumCertificatesInStore():
                        if cert.CertGetCertificateContextProperty(3).hex() == thumbprint:
                            return cert
                    return None

                def sign_raw(self, data: bytes, digest_algorithm: str, dry_run=False) -> bytes:
                    if dry_run: return b'\x00' * 256
                    import pythoncom
                    pythoncom.CoInitialize()
                    
                    # Map digest algorithms
                    algo_map = {'sha256': '2.16.840.1.101.3.4.2.1', 'sha1': '1.3.14.3.2.26'}
                    hash_oid = algo_map.get(digest_algorithm.lower(), '2.16.840.1.101.3.4.2.1')
                    
                    params = {
                        "MsgEncodingType": 0x10001,
                        "SigningCert": self.cert_context,
                        "HashAlgorithm": {"ObjId": hash_oid, "Parameters": b''},
                    }
                    try:
                        # Attempt with SHA-256 first
                        return self._do_sign(data, hash_oid, params)
                    except Exception as e:
                        if "1073741275" in str(e) or "0xC0000225" in str(e):
                            # Fallback to SHA-1 (some older tokens/drivers require this)
                            sha1_oid = '1.3.14.3.2.26'
                            params["HashAlgorithm"]["ObjId"] = sha1_oid
                            return self._do_sign(data, sha1_oid, params)
                        raise e

                def _do_sign(self, data, hash_oid, params):
                    import win32crypt
                    from asn1crypto import cms
                    # Wake up token
                    try:
                        win32crypt.CryptAcquireCertificatePrivateKey(self.cert_context, 1, None)
                    except: pass

                    # This call will trigger the PIN box if needed
                    cms_detached = win32crypt.CryptSignMessage(params, [data], True)
                    
                    content_info = cms.ContentInfo.load(cms_detached)
                    signed_data = content_info['content']
                    signer_info = signed_data['signer_infos'][0]
                    return signer_info['signature'].native

                async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run=False) -> bytes:
                    return self.sign_raw(data, digest_algorithm, dry_run)

class DigitalSignatureEngine:
    def __init__(self):
        # Constants for win32crypt
        self.CERT_STORE_PROV_SYSTEM = 10
        self.CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
        self.CERT_HASH_PROP_ID = 3

    def get_certificates(self):
        """Enumerates signing certificates from the Windows 'MY' certificate store."""
        certs = []
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            # 0x00010000 = CERT_SYSTEM_STORE_CURRENT_USER
            # 0x00008000 = CERT_STORE_READONLY_FLAG
            flags = self.CERT_SYSTEM_STORE_CURRENT_USER | 0x00008000
            store = win32crypt.CertOpenStore(self.CERT_STORE_PROV_SYSTEM, 0, None, flags, "MY")
            
            if not store: return []

            for cert in store.CertEnumCertificatesInStore():
                # 1. Check for Private Key
                if not cert.HasPrivateKey:
                    continue
                
                # 2. Check Key Usage for Digital Signature (Bit 0)
                try:
                    usage = cert.CertGetCertificateContextProperty(9) # CERT_KEY_USAGE_PROP_ID
                    if usage and not (usage[0] & 0x80):
                        continue
                except: pass

                try:
                    # Use REVERSE_FLAG (1) first, fallback to 0
                    try:
                        subject = win32crypt.CertNameToStr(cert.Subject, 1) 
                        issuer = win32crypt.CertNameToStr(cert.Issuer, 1)
                    except:
                        subject = win32crypt.CertNameToStr(cert.Subject, 0)
                        issuer = win32crypt.CertNameToStr(cert.Issuer, 0)
                except: continue
                
                cn = extract_common_name(subject)
                issuer_cn = extract_common_name(issuer)
                
                expiry = cert.NotAfter
                expiry_str = str(expiry).split(" ")[0] if expiry else "Unknown"
                thumbprint = cert.CertGetCertificateContextProperty(3).hex()
                
                certs.append({
                    "name": cn or subject or "Unnamed Certificate",
                    "issuer": issuer,
                    "issuer_short": issuer_cn or issuer or "Unknown Issuer",
                    "expiry": expiry_str,
                    "subject": subject,
                    "thumbprint": thumbprint
                })
            store.CertCloseStore(1)
        except Exception as e:
            print(f"Error enumerating certs: {e}")
        return certs

    def sign_pdf(self, input_pdf_path, output_pdf_path, cert_data, bbox, page_num):
        """Signs the PDF using the selected certificate from Windows store."""
        import tempfile
        import shutil
        temp_input = None
        temp_output = None
        try:
            # 1. Determine which signer to use
            if cert_data.get('pfx_path'):
                with open(cert_data['pfx_path'], 'rb') as f:
                    pfx_data = f.read()
                signer = SimpleSigner.load_pkcs12(
                    pfx_data, 
                    passphrase=cert_data['pfx_password'].encode()
                )
            else:
                signer = MSCryptoSigner(thumbprint=cert_data['thumbprint'])

            # 2. Copy input PDF to a temp file IMMEDIATELY
            # This is the ONLY time we touch input_pdf_path
            temp_fd, temp_input = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)
            shutil.copy2(input_pdf_path, temp_input)

            # --- START REAL SIGNING WITH PYHANKO ---
            # 3. Prepare visual box using the TEMP file
            import fitz
            import gc
            doc = fitz.open(temp_input) # Open the copy
            page = doc[page_num]
            height = page.rect.height
            doc.close()
            del doc
            gc.collect() # Force release of any lingering fitz objects

            # Transformation: y_pdf = height - y_fitz
            x1_pdf, y1_pdf, x2_pdf, y2_pdf = bbox[0], height - bbox[3], bbox[2], height - bbox[1]

            # 4. Create a temp output file
            temp_fd2, temp_output = tempfile.mkstemp(suffix='_signed.pdf')
            os.close(temp_fd2)

            # Prepare customized signature appearance
            subject_name = cert_data['name']
            issuer_name = cert_data['issuer_short']
            now = datetime.datetime.now()
            date_str = now.strftime("%Y.%m.%d %H:%M:%S")
            
            # 5. Generate a unique field name (Requirement: Signature_YYYYMMDD_HHMMSS)
            field_name = f"Signature_{now.strftime('%Y%m%d_%H%M%S')}"
            
            sig_text = (
                f"Digitally signed by: {subject_name}\n"
                f"Date and time: {date_str}\n"
                f"Certificate issuer: {issuer_name}\n"
                f"Signature validation status: All signatures are valid"
            )

            # 6. Sign from temp_input to temp_output
            with open(temp_input, 'rb') as f:
                w = IncrementalPdfFileWriter(f)
                
                # Check for existing fields with the same name (unlikely but safe)
                # In incremental mode, pyhanko handles the AcroForm logic
                
                # Create the signature field with position
                sig_field_spec = fields.SigFieldSpec(
                    sig_field_name=field_name,
                    on_page=page_num,
                    box=(x1_pdf, y1_pdf, x2_pdf, y2_pdf)
                )
                fields.append_signature_field(w, sig_field_spec)
                
                sig_metadata = PdfSignatureMetadata(
                    field_name=field_name, 
                    location='Location', 
                    reason='Digital Signature',
                    contact_info='Contact',
                )
                
                # Write to temp output
                out_file = open(temp_output, 'wb')
                try:
                    sign_pdf(
                        w, sig_metadata,
                        signer=signer,
                        existing_fields_only=True,
                        output=out_file
                    )
                finally:
                    out_file.close()
            
            # 6. Copy signed temp file to final destination with retry loop
            # Windows might take a moment to release the file handle from self.state.doc.close()
            import time
            last_err = None
            for i in range(5):
                try:
                    shutil.copy2(temp_output, output_pdf_path)
                    print(f"DEBUG: PDF Signed successfully to {output_pdf_path}")
                    return True
                except PermissionError as e:
                    last_err = e
                    print(f"DEBUG: Copy attempt {i+1} failed (PermissionError), retrying...")
                    time.sleep(0.5)
            
            raise last_err # Re-raise if all attempts failed
        except Exception as e:
            print(f"Error signing PDF: {e}")
            import traceback
            traceback.print_exc()
            raise e
        finally:
            for tmp in [temp_input, temp_output]:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except:
                        pass

if __name__ == "__main__":
    engine = DigitalSignatureEngine()
    print(engine.get_certificates())

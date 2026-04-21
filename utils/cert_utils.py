import re

def extract_common_name(subject_str):
    """
    Robustly extracts the person's name from an X.500 subject string.
    Prioritizes CN, Given Name, and Surname. Skips generic attributes and country codes.
    """
    if not subject_str:
        return "Unknown"
        
    # Standard attributes and their priority
    # We want to find the most "name-like" field
    
    # 1. Parse all attributes into a dictionary
    # Handles both "ATTR=VALUE" and "ATTR=\"VALUE\""
    attrs = {}
    # Split by comma but respect quoted values
    parts = re.findall(r'(?:[^,"]|"(?:[^"]|"")*")+', subject_str)
    for part in parts:
        if '=' in part:
            key, val = part.split('=', 1)
            attrs[key.strip().upper()] = val.strip().strip('"').replace('""', '"')
        else:
            # Fallback for parts without = (sometimes happens in raw strings)
            val = part.strip().strip('"')
            if val and val.upper() not in ["IN", "PERSONAL", "CLASS 2", "CLASS 3", "SIGNER"]:
                attrs['RAW_FALLBACK'] = val

    # 2. Priority check for names
    # Skip values that are just numbers (like '3148') or country codes
    def is_valid_name(v):
        if not v: return False
        v_clean = v.strip().upper()
        if v_clean in ["IN", "PERSONAL", "CLASS 2", "CLASS 3", "SIGNATURE", "TRUE", "FALSE"]: return False
        if v_clean.isdigit(): return False
        if len(v_clean) <= 2 and v_clean != "DR": return False # Skip 'IN', 'ST', etc.
        return True

    # Priority 1: Common Name (CN)
    if 'CN' in attrs and is_valid_name(attrs['CN']):
        return attrs['CN']
        
    # Priority 2: Given Name + Surname
    g = attrs.get('G', attrs.get('GIVENNAME', ''))
    sn = attrs.get('SN', attrs.get('SURNAME', ''))
    if is_valid_name(g) or is_valid_name(sn):
        return f"{g} {sn}".strip()
        
    # Priority 3: Any other field that looks like a name (Title, etc.)
    if 'T' in attrs and is_valid_name(attrs['T']):
        return attrs['T']
        
    # Priority 4: RAW_FALLBACK if it looks like a name
    if 'RAW_FALLBACK' in attrs and is_valid_name(attrs['RAW_FALLBACK']):
        return attrs['RAW_FALLBACK']
        
    # Priority 5: The first part of the string that isn't a known country/org code
    for part in parts:
        val = part.split('=')[-1].strip().strip('"')
        if is_valid_name(val):
            return val
            
    # Absolute Fallback: return what we have or the whole string
    return attrs.get('CN', parts[0].split('=')[-1].strip() if parts else subject_str)

if __name__ == "__main__":
    # Test cases
    test_cases = [
        'CN=ZALA JAYESHBHAI BHAGVANBHAI, O=Verasys Sub CA 2022',
        'CN="SMITH, JOHN", O=Testing Org',
        'IN, Personal, 3148, CN=John Doe',
        'O=Org, CN="Special Name"',
        'Just a name'
    ]
    for tc in test_cases:
        print(f"Subject: {tc} -> CN: {extract_common_name(tc)}")

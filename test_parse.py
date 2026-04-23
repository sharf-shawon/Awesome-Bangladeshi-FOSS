import re

def parse_issue(body):
    fields = {}
    current_key = None
    # Match headers like "### Project name"
    header_re = re.compile(r"^###\s+(.+)$")
    
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        
        match = header_re.match(line)
        if match:
            current_key = match.group(1).strip().lower().replace(" ", "_")
            continue
            
        if current_key:
            # Handle checkboxes
            if line.startswith("- [") and "]" in line:
                continue
            
            if current_key not in fields:
                fields[current_key] = line
            else:
                fields[current_key] += " " + line
    
    # Normalize values
    for k in fields:
        fields[k] = fields[k].strip()
    return fields

body = """### Project name

Awesome Bangladeshi Devs

### Repository URL

https://github.com/sharf-shawon/Awesome-Bangladeshi-Devs

### Short description

Awesome list of Top Performing Bangladeshi Developers on Github

### Category

Awesome Lists & Resource Collections

### Submission checklist

- [x] This project is genuinely free and open source.
- [x] This submission is not a duplicate of an existing README entry.
- [x] I used a GitHub repository URL in the format https://github.com/owner/repo.

### Reconsideration notes

_No response_"""

print(parse_issue(body))

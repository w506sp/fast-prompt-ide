import re

def extract_variables(content):
    """Return unique variable names found as {{name}} in prompt content."""
    return list(set(re.findall(r'\{\{(\w+)\}\}', content)))

def render_prompt(content, values):
    """Substitute {{name}} placeholders with values dict."""
    def replace(match):
        return values.get(match.group(1), match.group(0))
    return re.sub(r'\{\{(\w+)\}\}', replace, content)

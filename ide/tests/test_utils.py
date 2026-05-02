from django.test import SimpleTestCase

from ide.utils import extract_variables, render_prompt


class ExtractVariablesTests(SimpleTestCase):
    def test_finds_unique_names(self):
        names = extract_variables("hello {{name}}, your code is {{code}} and {{name}} again")
        self.assertEqual(set(names), {"name", "code"})

    def test_no_variables(self):
        self.assertEqual(extract_variables("plain prompt"), [])

    def test_ignores_malformed(self):
        # single braces / spaces inside / non-word chars are not matched
        self.assertEqual(extract_variables("{ name } {{ spaced }} {{bad-name}}"), [])


class RenderPromptTests(SimpleTestCase):
    def test_substitutes_known_values(self):
        out = render_prompt("hi {{name}}", {"name": "ada"})
        self.assertEqual(out, "hi ada")

    def test_leaves_unknown_placeholder_intact(self):
        out = render_prompt("hi {{name}} {{missing}}", {"name": "ada"})
        self.assertEqual(out, "hi ada {{missing}}")

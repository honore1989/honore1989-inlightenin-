import unittest
from inlightenin import execute, InLighteninError


class InLighteninTests(unittest.TestCase):
    def test_assignment_and_output(self):
        result = execute("Lit1 = \"Hello\"\nIN (Lit1)")
        self.assertEqual(result, ["Hello"])

    def test_undefined_variable(self):
        with self.assertRaises(InLighteninError):
            execute("IN (Lit1)")


if __name__ == "__main__":
    unittest.main()
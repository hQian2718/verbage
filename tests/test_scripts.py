import unittest

from dialogbot.expressions import eval_condition, validate_condition
from dialogbot.parser import load_game


class FakeContext:
    def __init__(self, text="") -> None:
        self.text = text
        self.variables = {"answer": text}

    async def get_var(self, name):
        return self.variables[name]

    async def set_var(self, name, value):
        self.variables[name] = value

    async def wait_for_input(self):
        return self.text

    def username(self):
        return "tester"


class ScriptTests(unittest.IsolatedAsyncioTestCase):
    def test_sample_scripts_load(self):
        game = load_game("game")
        self.assertIn(("main", "setup"), game.labels)
        self.assertIn(("interior", "restroom_2"), game.labels)

    async def test_contains_sugar_with_input(self):
        expression = 'input() contains "portrait" or "winnie" or "investigate"'
        validate_condition(expression, {})
        self.assertTrue(await eval_condition(expression, FakeContext("look at portrait")))
        self.assertTrue(await eval_condition(expression, FakeContext("WINNIE")))
        self.assertFalse(await eval_condition(expression, FakeContext("wash hands")))

    async def test_contains_sugar_with_variable(self):
        expression = 'answer contains "dead" or "beef"'
        validate_condition(expression, {"answer": ""})
        self.assertTrue(await eval_condition(expression, FakeContext("dead beef")))
        self.assertFalse(await eval_condition(expression, FakeContext("nothing")))


if __name__ == "__main__":
    unittest.main()

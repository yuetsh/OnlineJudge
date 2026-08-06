from unittest import TestCase

from reaction.models import Reaction
from reaction.serializers import SetReactionSerializer


class SetReactionSerializerTests(TestCase):
    def test_accepts_one_reaction(self):
        serializer = SetReactionSerializer(data={"problem_id": 1, "type": "learned"})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["type"], "learned")

    def test_rejects_missing_reaction(self):
        serializer = SetReactionSerializer(data={"problem_id": 1})

        self.assertFalse(serializer.is_valid())
        self.assertIn("type", serializer.errors)

    def test_rejects_unknown_reaction(self):
        serializer = SetReactionSerializer(data={"problem_id": 1, "type": "unknown"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("type", serializer.errors)


class ReactionModelConstraintTests(TestCase):
    def test_one_reaction_per_problem_and_user(self):
        constraints = {constraint.name: constraint for constraint in Reaction._meta.constraints}

        constraint = constraints["reaction_problem_user_unique"]
        self.assertEqual(tuple(constraint.fields), ("problem", "user"))

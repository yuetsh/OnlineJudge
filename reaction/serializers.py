from reaction.models import ReactionType
from utils.api import serializers


class SetReactionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=ReactionType.choices)

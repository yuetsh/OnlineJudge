from reaction.models import ReactionType
from utils.api import serializers

MAX_REACTIONS = 3


class SetReactionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    types = serializers.ListField(
        child=serializers.ChoiceField(choices=ReactionType.choices),
        allow_empty=True,
    )

    def validate_types(self, value):
        unique = list(dict.fromkeys(value))
        if len(unique) > MAX_REACTIONS:
            raise serializers.ValidationError(f"最多只能选 {MAX_REACTIONS} 个")
        return unique

from reaction.models import ReactionType
from utils.api import serializers


class SetReactionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=ReactionType.choices, required=False)
    types = serializers.ListField(
        child=serializers.ChoiceField(choices=ReactionType.choices),
        required=False,
        allow_empty=False,
    )

    def validate(self, attrs):
        reaction_type = attrs.get("type")
        legacy_types = list(dict.fromkeys(attrs.get("types", [])))

        if len(legacy_types) > 1:
            raise serializers.ValidationError({"types": "只能选择一个评价"})
        if reaction_type is None and not legacy_types:
            raise serializers.ValidationError({"type": "This field is required."})
        if reaction_type is not None and legacy_types and reaction_type != legacy_types[0]:
            raise serializers.ValidationError({"types": "新旧评价字段不一致"})

        attrs["type"] = reaction_type or legacy_types[0]
        return attrs

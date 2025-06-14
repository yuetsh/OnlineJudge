from rest_framework import serializers
from .models import Tutorial
from account.serializers import UserSerializer

class TutorialSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    
    class Meta:
        model = Tutorial
        fields = ['id', 'title', 'content', 'created_by', 'created_at', 
                 'updated_at', 'is_public', 'order']
        read_only_fields = ['created_by', 'created_at', 'updated_at'] 
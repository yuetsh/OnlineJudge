from ..api import APIView
from ..shortcuts import img2base64
from . import Captcha


class CaptchaAPIView(APIView):
    def get(self, request):
        return self.success(img2base64(Captcha(request).get()))

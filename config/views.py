from django.shortcuts import render


def error_400(request, exception=None):
    return render(request, "errors/error.html", {"code": 400, "title": "Bad request", "message": "The request could not be processed."}, status=400)


def error_403(request, exception=None):
    return render(request, "errors/error.html", {"code": 403, "title": "Access denied", "message": "You do not have permission to open this page."}, status=403)


def error_404(request, exception=None):
    return render(request, "errors/error.html", {"code": 404, "title": "Page not found", "message": "The page you are looking for does not exist or was moved."}, status=404)


def error_500(request):
    return render(request, "errors/error.html", {"code": 500, "title": "Server error", "message": "Something went wrong. Please try again after a moment."}, status=500)

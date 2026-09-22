from rest_framework.renderers import JSONRenderer

SUCCESS_MESSAGES = {
    'POST': 'Created successfully',
    'PUT': 'Updated successfully',
    'PATCH': 'Updated successfully',
    'DELETE': 'Deleted successfully',
}

ERROR_MESSAGES = {
    400: 'Validation failed',
    401: 'Authentication required',
    403: 'Permission denied',
    404: 'Not found',
    405: 'Method not allowed',
    # 409 is the PROTECT-ed delete. It is worth its own wording rather than the
    # generic fallback, because "Something went wrong" tells a user to retry
    # while "other records depend on this one" tells them what to fix.
    409: 'Cannot delete: other records depend on this one',
    415: 'Unsupported media type',
}


class APIResponseRenderer(JSONRenderer):
    """Wraps every DRF response into a consistent {success, message, data,
    errors} shape. This is the ONLY place response shaping happens — views
    and serializers never build this envelope themselves."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get('response')
        request = (renderer_context or {}).get('request')
        status_code = response.status_code if response else 200
        is_success = status_code < 400
        method = request.method if request else 'GET'

        wrapped = {
            'success': is_success,
            'message': (
                SUCCESS_MESSAGES.get(method, 'Success') if is_success
                else ERROR_MESSAGES.get(status_code, 'Something went wrong')
            ),
            'data': data if is_success else None,
            'errors': None if is_success else data,
        }
        return super().render(wrapped, accepted_media_type, renderer_context)

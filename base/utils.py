from django.http import Http404

import base.exceptions as exceptions

def create_resource(serializer, user):
    '''
    This function is used to get around making API calls
    between different endpoints.  Namely, when a user requests
    the "upload" endpoint, we have to create Resource objects.
    To keep Resource creation in a central location, we extracted the logic
    out of the API view and put it here.  Then, any API endpoint needing to
    create one or more Resource instances can use this function instead of
    having to call the endpoint for creating a Resource.

    serializer is an instance of rest_framework.serializers.ModelSerializer
    user is a basic Django User (or subclass)
    '''
    serializer.is_valid(raise_exception=True)

    # if the user is NOT staff, we only let them
    # create a Resource for themself.
    if not user.is_staff:
        # if the owner specified in the request is the requesting user
        # then we approve
        try:
            many = serializer.many
        except AttributeError as ex:
            many = False
        if many:
            owner_status = []
            for item in serializer.validated_data:
                try:
                    properly_owned = item['owner'] == user
                    owner_status.append(properly_owned)
                except KeyError as ex:
                    item['owner'] = user
                    owner_status.append(True)
            if all(owner_status):
                return serializer.save()
            else:
                raise exceptions.RequestError('Tried to create a Resource attributed to someone else.')  
        else:
            try:
                if serializer.validated_data['owner'] == user:
                    return serializer.save()
                # here we block any effort to create a Resource for anyone else.
                #Raise 404 so we do not give anything away
                else:
                    raise Http404
            except KeyError as ex:
                return serializer.save(owner=user)

    # Otherwsie (if the user IS staff), we trust them to create
    # Resources for themselves or others.
    else:
        return serializer.save()
from base.models import Resource

def map_inputs(user, unmapped_data, id_list):
    '''
    `user` is a User instance (or subclass).  This gives us
    the option of applying user-specific logic to the mapping.
    Since the code that calls this function does NOT know
    the structure of the input data, it cannot impose any logic
    such as filtering Resource objects for a particular user.
    Therefore we have to keep that information here

    `unmapped_data` is some data structure sent by
    the frontend.  The structure is known to the 
    developer since they specified the input element responsible
    for creating the data.  For example, a file chooser will send
    a list/array of primary keys.

    `id_list` is a list of WDL input "names"/ids that we are mapping
    to. 

    In this simple version, the basic file chooser sends a list
    of primary keys for Resource elements.  This identifies the files
    to be used as input to the workflow.

    The id_list is a one-element list with the name ("TestWorkflow.inputs")
    of a WDL input the accepts a Array[File].  Thus, we need to eventually
    product a WDL input file that looks like:

    {
        ...
        "TestWorkflow.inputs": ["fileA.txt", "fileB.txt"]
        ...
    }

    Therefore, the goal here is to use the PKs to query for filenames, which
    are then held in a list.  We return a dict:
    {"TestWorkflow.inputs": ["fileA.txt", "fileB.txt"]}
    '''
    path_list = []
    for pk in unmapped_data:
        r = Resource.objects.get(pk=pk)
        if r.owner == user:
            path_list.append(r.path)
        else:
            raise Exception('The user %s is not the owner of Resource with primary key %s.' % (user, pk))
    return {id_list[0]:path_list}

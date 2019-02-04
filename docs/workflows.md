### CNAP Guide: Creating and adding new WDL-based workflows

The CNAP is designed to ingest WDL-based workflows and run on the Cromwell execution engine.  This guide assists in the creation and ingestion of workflows, including the specification of the custom UI elements that accompany each workflow.

In this document there are three primary "roles" described-- the CNAP admin, the developer, and the client.  Reference to these roles is made in a consistent manner below.  
- The **admin** has superuser privileges, including logging into the application server, running the application Docker container, etc.  They can do anything.
- A **developer** is someone who might write a WDL-based workflow that performs some analysis.  They *could* have admin privileges, but might not.  For instance, the CNAP admins might work with an academic group who has developed an analysis workflow they would like to "publish" using the CNAP.  Rather than learning how to work with the platform, they might just simply create a WDL script and send that to the CNAP admin.
- A **client** is the end-user of the application.  Typically this would be someone who has no particular knowledge of bioinformatics and/or programming.  This might be a bench-scientist running a simple differential gene expression.  They have accounts on the CNAP and are able to execute analyses through the web-based interfaces provided by the CNAP. 

#### Before starting-- about your WDL
Before attempting to integrate any WDL-based workflows into CNAP, the developer should ensure that the workflow is stable and robust.  CNAP simply provides the ability to wrap workflows with a simple GUI (and file transfer utilities) so that analyses can be made accessible and distributable through a web-based platform.  CNAP is not responsible for debugging WDL.  Thus, at the point of integrating with CNAP, your workflow should be "production-ready".

The only additional "requirement" for the WDL (which is not enforced), is that you include a `meta` section inside the main workflow directive.  This aids with the organization and display of workflows within CNAP.  There are three keys we look for:
```
meta {
    workflow_title : "Exome tumor-normal analysis"
    workflow_short_description : "For exomes variant analysis"
    workflow_long_description : "Use this workflow for analyzing matched tumor normal pairs that were sequenced using whole-exome sequencing technology.  The analysis starts from fastq-format input files and creates a VCF file of high-quality variants at the end"
}
```
These fields provide more detail about the analysis, which can help both admins and users with selections.  If they are not specified, they are left empty.


#### Creating a new workflow

Provided a working WDL file (or set of WDL files), someone with admin privileges should create a new directory somewhere *inside* the Docker container running the CNAP application.  Alternatively, they may create a directory on the host VM assuming it is mounted to your Docker container (and thus readable by the container).  All workflow files will be placed there.

**Required files**:

At minimum, you need two files to be placed into this directory- 
- `main.wdl`: Your "main" WDL file.  **Must** be named "main.wdl" and contain a `workflow` directive.
- `gui.json`: A JSON-format file which dictates how to construct the HTML GUI.  See section below.

In addition to these files, there may be *other* WDL files, supporting use-cases where one might save WDL tasks in separate files, or cases where workflows execute sub-workflows (in the WDL/Cromwell nomenclature).  They are located by the `.wdl` extension, so *only* files ending with that prefix will be found.  

There may also be python files, which assist in mapping the GUI inputs to the WDL inputs.  We show an example of this below.

Note that the `gui.json` file can be created by either the developer *or* the admin (or a combination of effort).  Since creation of a proper GUI might require some debugging/iterations to get correct, this task would likely fall more into the realm of the CNAP admin.  Additionally, the CNAP admin might be more familiar with creating the `gui.json` file whereas a developers effort would be focused on a robust WDL workflow. 

**Ingesting the workflow**
After all the files are located in the same directory, the admin runs the ingestion script (from inside the Docker container), passing the path to the directory with the `-d` argument:
```python3 <repository dir>/workflow_ingestion/ingest_workflow.py -d <workflow dir>```

If successful, this script will create a series of directories under `<repository dir>/workflow_library/`, which will be identified by the name of the workflow and a unique identifier (e.g. `<repository dir>/workflow_library/<workflow name>/<string>/`).  The workflow will be added to the database.

Multiple workflows with the same name will be "versioned" so that there are no conflicts and older workflows may be recalled/re-run for reproducible analyses.  *Note that by default, newly ingested workflows are **not** live-- they must be activated by logging into the admin console and editing the database to set the workflow to the `active=True` status*.  Additionally, one can edit the database to set a particular version of a workflow as the default.  Thus, requests to run a workflow that do not require a specific version will use the version marked as "default".   

If there is a problem during workflow ingestion, an error message should help guide you; preliminary files end up being "staged" in a subdirectory inside `<repository dir>/workflow_ingestion/staging/`, which can help with debugging. 

#### Specifying the GUI

A WDL workflow typically has a number of inputs, such as file paths, strings, numbers, etc.  With CNAP, we allow developers to create basic user-interfaces that allow application users (clients) to specify those inputs.  For example, a CNAP user might have some fastq-format sequence files that have been uploaded.  The GUI would allow them to select files for downstream analysis.  There may also be inputs for items like reference genome selection.  The `gui.json` file allows the workflow developer to specify the GUI elements and how they behave.  

We first show a basic `gui.json` which demonstrates the core set of GUI elements, and will cover the majority of use-cases.  We then discuss the GUI creation in more generality, including descriptions on how to write python-based scripts which customize data tranformations behind-the-scenes.  We aim to provide concrete examples which cover a broad range of applications.

**Example walkthrough**

Here we demonstrate how to create the following GUI for a dummy exome analysis workflow:
![alt text](exome_ss.png)

We are creating a GUI for the following dummy WDL, which we show in part below; we only show the inputs since that is the only relevant part for constructing a GUI:

```
workflow ExomeWorkflow {
    
    Array[File] tumorSamples
    Array[File] normalSamples
    String outputFilename
    String genomeChoice

    ...<other WDL>...
}
```
Thus, we have four inputs: two arrays of files (tumor and normal), a string giving the name of an output file, and a string giving the choice of genome.  This is NOT an actual workflow, so the inputs here are purely for illustration.

The following `gui.json` was used to create the GUI above. We discuss each element, its attributes, and other important points.  
```
{
	"input_elements": [
		{
			"target": {
				"target_ids": ["ExomeWorkflow.normalSamples", "ExomeWorkflow.tumorSamples"],
				"name": "input_files",
				"handler": "input_mapping.py"
			},
			"display_element": {
				"type": "file_chooser",
				"context_args": {"filter":".*fastq.gz"},
				"label": "Input files:",
				"choose_multiple": true,
				"description": "Choose both tumor and normal samples for the analysis"
			}	
		},
		{
			"target": "ExomeWorkflow.outputFilename",
			"display_element": {
				"type": "text",
				"label": "Output filename:",
				"description": "Name the output file...",
				"placeholder": "Name the output file..."
			}	
		},
                {
			"target": "ExomeWorkflow.genomeChoice",
			"display_element": {
				"type": "select",
				"label": "Genome:",
				"description": "Choose the reference genome",
                                "choices": [{"value":"hg38", "display":"Human HG38"},{"value":"m38","display":"Mouse GRCm38"}]
			}	
                }
	]
}

```

At the root of this JSON object, note that we only require a single key `"input_elements"` which points at a list of objects (here, 3 objects).  Each item in the list dictates an input element in the GUI (a file-chooser, a text box, and a dropdown, in order).

Each input element object has two required keys: `"target"` and `"display_element"`.  The `"target"` key can point at either a string (see items 2 and 3) or a JSON object (see item 1), while the `"display_element"` always points at a JSON object.

We first examine the second element of the `input_elements` array, which corresponds to a text box in the GUI:
```
{
    "target": "TestWorkflow.outputFilename",
    "display_element": {
        "type": "text",
        "label": "Output filename:",
        "placeholder": "Name the output file..."
    }	
}
```
In this input element, the `"target"` attribute points at a string, and the format corresponds to `<workflow name>.<input name>`.  Recall above that our workflow was named `ExomeWorkflow`.  We wish to use this GUI input to provide the output filename, which is given as `outputFilename` in the WDL above.  Hence the string is `"ExomeWorkflow.outputFilename"`.

Within the display object (addressed by the `"display_element"` key), we see that we would like a `"text"` input, which corresponds to a basic HTML text field input.  The `"label"` will clearly label the text box, and the `"placeholder"` attribute fills in the help text.

Note that our choice of `"type": "text"` was not arbitrary-- the value "text" corresponds to one of the pre-defined UI elements that are available in the GUI schema discussed in the following section.  Furthermore, the selection of keys inside this display element object (e.g. "label", "placeholder") is determined by the chosen input element type; each type of input element (text box, dropdown, etc.) has a set of available keys.  Some keys are required, while others provide default values.

The next element is the dropdown, which we copy here:
```
{
    "target": "ExomeWorkflow.genomeChoice",
    "display_element": {
        "type": "select",
        "label": "Genome:",
        "description": "Choose the reference genome",
        "choices": [
            {"value":"hg38", "display":"Human HG38"},
            {"value":"m38","display":"Mouse GRCm38"}
        ]
    }	
}
```
Once again, `"target"` points at a string, and we see that this corresponds to the "genomeChoice" input to the WDL workflow named "ExomeWorkflow"; the input is a string, but we want to only allow a few pre-defined options.  Thus, we ask for a dropdown (`"type": "select"`), label it, provide a description (which is not shown anywhere, but can be helpful for notes), and specify the choices available in this dropdown.

When we specify the options, we use the simple list of JSON objects as shown.  The use of "value" and "display" in those objects is not arbitrary, but is linked to the HTML template code that defines the dropdown.  If you are creating simple dropdowns in this same manner, then it is enough to just copy this and edit to your liking.  However, this dropdown example also provides a good example of how one might choose to define their own custom GUI elements, which we discuss in a later section.

The final element is the file chooser, which is itself a complete example of how to create a fully custom element that includes HTML, javascript, css, and custom "handler" code for the backend.  We "briefly" discuss here, but return to this in further detail below.  For reference, we copy here again:  

```
{
    "target": {
        "target_ids": ["ExomeWorkflow.normalSamples", "ExomeWorkflow.tumorSamples"],
        "name": "input_files",
        "handler": "input_mapping.py"
    },
    "display_element": {
        "type": "file_chooser",
        "context_args": {"filter":".*fastq.gz"},
        "label": "Input files:",
        "choose_multiple": true,
        "description": "Choose both tumor and normal samples for the analysis"
    }	
}
```

For the moment we note that the `target` key does not point at a string, but instead points at an object (first time we have seen this).  For the text and dropdown discussed prior, `target` pointed at a string and there was an obvious one-to-one mapping of the GUI input element and the WDL input.  The backend is able to directly associate the data captured in the UI element and the data that needs to be supplied to the WDL workflow.  

By having `target` point at an object, we allow for input elements to map to potentially >=1 WDL inputs.  Our dummy WDL accepts *separate* arrays for the tumor and normal sequence files.  However, we may only want to display a single file-chooser, and let our backend apply logic to determine tumor and normal samples.   This object-based `target` allows for exactly this type of flexibility.

The `target_ids` list dictates the >=1 WDL inputs that this element will map to.  Note that even if you are only mapping to a single WDL input, you need to phrase it as a list.  The key `handler` points to a Python file that handles data transformations.  That is, once data is received from the front-end, the code contained in that file will manipulate that data to produce the correct inputs for the WDL.  For example, our front-end might return a list of integers which represent the primary keys of the selected files.  The code in the handler will take those primary keys, apply some logic, and return a data structure that is compatible with the WDL.  For a concrete example, see "backend mapping" below.

Discussion of the `display_element` for the file-chooser is reserved for the section concerning the creation of custom input elements.  However, we briefly note that the `context_args` parameter specifies that the file-chooser we created should filter to *only* show gzipped fastq-format files.

#### The GUI schema

As described above, we compose the user-interface from a set of pre-defined elements, using our `gui.json` file to dictate how those elements are shown (e.g. labels, dropdown choices, etc).  The full set of these elements is given in `<repository dir>/workflow_ingestion/gui_schema.json`.  In that file, we see the `gui_elements` key, which points at a JSON object.  Each key in this object gives the "name" of an available element.  Recall that in our `gui.json` file, we declared "types" for each element in our GUI; you *must* select an element that is among the keys of the `gui_elements` object.  For instance, in our GUI above we created a dropdown by declaring `"type": "select"`, which is one of the keys in the `gui_elements` object.

Each of these GUI elements has several keys:
- `html_source` gives the location (relative to the `workflow_ingestion` directory) of an HTML snippet which declares how it is displayed in the browser.  These HTML snippets often include "template" code for the python-based jinja templating language.  As a concrete example, consider the snippet for the dropdown element used above:

    ```
    <div class="form-group">
        <h4><label for="select-{{id}}">{{label}}</label></h4>
        <select 
                class="form-control" 
                id="select-{{id}}" 
                name="{{name}}" 
                required 
                dataTarget="{{name}}"
                {% if choose_multiple %}
                    multiple
                {% endif %}
            >
            {% for d in choices %}
            <option value="{{d.value}}">{{d.display}}</option>
            {% endfor %}
        </select>
    </div>
    ```
    The items enclosed in double braces `{{...}}` denote jinja template tags that are dynamically filled.  After describing the javascript handlers and parameters below, we will return to this snippet to further discuss the templating.

  If you wish to create your own element and need some dynamic behavior (e.g. via javascript), you should include it in the HTML snippet inside `<script></script>` tags.  The javascript contained there should *only* be related to display and/or dynamic UI behavior.  Javascript used to "prepare" data to be POST'd to the backend is declared in the `js_handler` file.

- `js_hander` points at another file which contains javascript dictating how the data captured from the input element is transformed before being sent to the backend.  Often optional.  An example is the file at `<repository dir>/workflow_ingestion/js/file_chooser.js` which is a handler for our custom file chooser interface.  This code is executed when the client clicks "analyze"; the javascript (using jQuery) goes through the file chooser interface to determine which files were selected for analysis.  It then extracts unique identifiers for those resources (e.g. primary keys) which are subsequently included in the data that is sent to the backend.  As briefly mentioned above, the javascript contained in the `js_handler` is only executed just prior to POSTing content to the backend; it does *not* control any dynamic behavior of the interface itself.

    Many of the "simple" input elements (e.g. text boxes, dropdowns) directly transmit their data and do *not* need to define a `js_handler`, so it is often set to `null`.  For example, in the dropdown, the selected option is sent to the backend referenced by the `name` attribute in the `<select>` element.  As a concrete example, consider the following HTML specifying a dropdown: 
    ```
    <select 
            class="form-control" 
            id="select-2" 
            name="TestWorkflow.genomeChoice" 
            required 
            dataTarget="AAATestWorkflow.genomeChoice">

          <option value="hg38">Human HG38</option>
          <option value="grcm38">Mouse GRCm38</option>
    </select>
    ```  
    When the form containing this element is submitted, the payload sent to the backend will contain (among other parts): `{"TestWorkflow.genomeChoice": "hg38"}` assuming "Human HG38" was selected.  In that case, we have a direct association between the WDL input `TestWorkflow.genomeChoice` and the string `hg38` and there is no need for a custom `js_handler` to transform the data.

-  `parameters` is a list of available parameters to customize the display or behavior of the input element.  Each item in the `parameters` list is itself an object.  Depending on the particular element, this list is different.  For instance, the text input defines a "placeholder" parameter which provides "hints" in the text box (see the example above where we used the placeholder).  Such a parameter would not be relevant for a dropdown menu.  

    Some of the parameters are marked as "required", as the interface would not be sensible without them (e.g. the choices for a dropdown menu).  Others define basic defaults, such as the maximum length of a text box.  If you neglect to provide a "required" parameter in your `gui.json`, the ingestion script will fail.  If you omit a non-required parameter, the default (if any) will be auto-filled.

Returning to the example of the dropdown menu, we copy the corresponding portion from `gui_schema.json`:
```
"select": {
    "html_source": "html_elements/select_input.html",
    "js_handler": null,
    "parameters": [
        {
            "name": "choices",
            "type": "list of objects",
            "required": true
        },
        {
            "name": "label",
            "type": "string",
            "required": false,
            "default": ""
        },
        {
            "name": "description",
            "type": "string",
            "required": false,
            "default": ""
        },
        {
            "name": "choose_multiple",
            "type": "bool",
            "required": false,                
            "default": false
        }
    ]
}
```

The `html_source` gives the path to the HTML file, which we had copied in a listing above.  There is no need for custom handler code, so `js_handler` is simply null.  Finally, we note that there is only a single required parameter, which dictates the choices available in the dropdown menu.  Note that the type of "list of objects" is simply a cue-- it does not define any specific data structure that must be constructed.  The structure is dictated by the HTML template, which we cover in detail below.  The other parameters are optional. The final parameter `choose_multiple` allows one to create a menu where multiple selections are possible; by default it only allows a single selection, yielding a standard dropdown menu.

**Connecting everything**
In this section, we "close the loop" on how the HTML template, the `gui_schema.json`, and the user-defined `gui.json` work together to create the final UI.  A more advanced example is covered in the section where we discuss the file-chooser element, but here we focus this discussion around the `select` element and the `choices` parameter.

Note that in the HTML template, we have the following "for" loop (in jinja syntax):
```
...
{% for d in choices %}
    <option value="{{d.value}}">{{d.display}}</option>
{% endfor %}
...
```
In this loop we iterate over `choices`, which requires that `choices` is some iterable data structure (a list, in this case).  The looping variable `choices` is directly tied to the `"name": "choices"` given in `gui_schema.json`.  Note that as part of the loop, we expect each temporary loop variable `d` to have keys of `value` and `display`.  With that in mind, recall how we specified our dropdown choices in the example `gui.json` above:
```
{
    "target": "TestWorkflow.genomeChoice",
    "display_element": {
        "type": "select",
        "label": "Genome:",
        "description": "Choose the reference genome",
        "choices": [
            {"value":"hg38", "display":"Human HG38"},
            {"value":"m38","display":"Mouse GRCm38"}
        ]
    }	
}
```

The data structure referenced by `choices` indeed meets the requirements of the HTML template (it is a list where each item contains keys `value`, `display`).  In this manner one can define new input elements that will accept essentially arbitrary data.

#### Backend mapping

In our earlier dummy example where we were describing the `gui.json` for a hypothetical exome pipeline, the file-input section looked like:

```
{
    "target": {
        "target_ids": ["ExomeWorkflow.normalSamples", "ExomeWorkflow.tumorSamples"],
        "name": "input_files",
        "handler": "input_mapping.py"
    },
    "display_element": {
        "type": "file_chooser",
        "context_args": {"filter":".*fastq.gz"},
        "label": "Input files:",
        "choose_multiple": true,
        "description": "Choose both tumor and normal samples for the analysis"
    }	
}
```

Previously, we vaguely described that the `handler` key pointed at a Python file that performed some data transformations to map the GUI inputs to the WDL inputs.  To aid with understanding, we present a concrete example below.  

For our toy example, the client would select files to analyze, among the other inputs.  Upon clicking "analyze", a JSON payload is POSTed to the backend where the workflow is prepared and initiated.  In this case, the front-end happens to return a list of integers, which correspond to primary keys for file resources tracked in our database.  The WDL workflow, on the other hand, is expecting filepaths; if we are operating on GCP, these paths can be in Google storage buckets, e.g. `gs://<bucket>/<object name`>.  It is the job of the `handler` to perform this tranformation.  

We require that the Python file contain a function named `map_inputs` with the following signature:
```
def map_inputs(user, unmapped_data, id_list):
    ...do stuff...
```
Here, `user` is a Django User model (or derived subclass).  This allows us to perform checks that are dependent on the user (e.g. checking that they "own" the files).  The second argument `unmapped_data` is the "raw" data POSTed to the backend.  Note that it's not ALL the data (i.e. it does not include the genome choice), only the data corresponding to this input element.  In our case, it's simply a list of integers.  Finally, `id_list` is the list of WDL inputs, taken from the `target_ids` field.  In our example, it is `["ExomeWorkflow.normalSamples", "ExomeWorkflow.tumorSamples"]`.

For a concrete example:
```
from base.models import Resource

def map_inputs(user, unmapped_data, id_list):
    normal_path_list = []
    tumor_path_list = []
    for pk in unmapped_data:
        r = Resource.objects.get(pk=pk)
        if r.owner == user:
            if r.path.endswith('_N.fastq.gz'):
                normal_path_list.append(r.path)
            elif r.path.endswith('_T.fastq.gz'):
                tumor_path_list.append(r.path)
            else:
                pass # unrecognized suffix.  Silently skip.
        else:
            raise Exception('The user %s is not the owner of Resource with primary key %s.' % (user, pk))
    return {id_list[0]:normal_path_list, id_list[1]:tumor_path_list}
```

In this example, we iterate through the integer primary keys (PK) supplied by the front end.  For each PK we lookup the file `Resource`, check that it "belongs to" the client, and decide if it's a tumor or normal sample based on the filename.  In this way, we populate lists containing paths to the files we will analyze.  Of course, the logic here is completely arbitrary and dependent on your application.  A more robust example might include logic to ensure that all the files are properly paired.   


#### Creation of custom elements (advanced, optional)

The CNAP provides a set of native HTML input elements with reasonable defaults "out of the box".  We also include custom a file-chooser element, as selection of files is a common input to many analysis pipelines.  The file-chooser also provides a complete and instructive example of how to create new, complex input elements for the CNAP GUI, if desired.

The first step in the creation of any custom element is to design and write the HTML.  Following that, one can reverse-engineer the customizable portions and specify those as parameters in the `gui_spec.json` file.  For a concrete example, let's look at the HTML file supporting the file-chooser element: 

```
<h4>
    {{label}}
</h4>
<p>
    {{description}}
</p>
<table id="chooser-table-{{id}}" class="custom-table"
    {% if choose_multiple %}
    multiple-select-enabled
    {% endif %}
    dataTarget="{{name}}"
>
    <thead>
        <tr>
            <th>
                {% if choose_multiple %}
                <input 
                    class="select-all-cbx" 
                    table-target="chooser-table-{{id}}" 
                    type="checkbox"/>
                {% endif %}

            </th>
            <th>Filename</th>
            <th>File size</th>
        </tr>
    </thead>
    <tbody>
        {% raw %}
        {% for resource in user_resources %}
        <tr>
            <td>
                <input class="download-selector" type="checkbox" target="{{resource.id}}"/>
            </td>
            <td>
                {{resource.name}}
            </td>
            <td>
                {{resource.human_readable_size}}
            </td>
        </tr>
        {% endfor %}
        {% endraw %}
    </tbody>
</table>

<script>
// javascript that allows us to create a "Select all" button
// in the file-chooser:
$(".select-all-cbx").click(function(){
    var targetedTable = $(this).attr("table-target");
    var inputs = $("#" + targetedTable).find("input");

    if ($(this).prop("checked") == true){
        $(inputs).each(function(number, el){
            $(el).prop("checked", true);
        });
    }else{
        $(inputs).each(function(number, el){
            $(el).prop("checked", false);
        });                }

});
</script>
```
Here, we see that the file-chooser is basically a plain HTML table.  For initial design mockup, it might make sense to hardcode everything and see how it looks (including mock data, like files).  Then, work backwards to "template" portions that can or should be dynamic.  Above, we see template elements like `{{label}}` and  `{{description}}` that are *always* displayed regardless of the client.  Other portions, however, have template code that is wrapped in `{% raw %}...{% endraw %}` tags; notably, those portions correspond to content that will be client-dependent.  Therefore, any client-dependent templated content *needs* to be wrapped in the "raw" tags.  

We need to do this because our GUI construction ultimately happens in two steps.  When we initially integrate the workflow into CNAP using the `ingest_workflow.py` script, we use the developer-supplied `gui.json` file to fill-in those client-independent portions such as `{{label}}`; that user-independent content will be shown to all clients and will never change.  In that first templating pass, the portions wrapped in `{% raw %}...{% endraw %}` will be ignored, except that the "raw" tag wrappers themselves will be removed.  This "first pass template" is saved as the workflow's template, and is ready to display dynamic, user-dependent content (file information, in this case) when the workflow is served by the application.

We also note the inclusion of the javascript in the `<script>...</script>` tags.  As mentioned above, the javascript contained in the HTML template is used to control interactive/dynamic behavior.  Here, it is used to provide a "check/uncheck all" option at the top of the table.  You may use jQuery syntax, as the library is imported earlier in the HTML file.  

**Adding user-dependent content**
In the HTML above, after the first pass of templating, we end up with an HTML file that contains only templates related to content that is served in realtime, and dependent on the particular client.  Extracting that portion from the snippet above, we have:
```
{% for resource in user_resources %}
<tr>
    <td>
        <input class="download-selector" type="checkbox" target="{{resource.id}}"/>
    </td>
    <td>
        {{resource.name}}
    </td>
    <td>
        {{resource.human_readable_size}}
    </td>
</tr>
{% endfor %}
```
Thus, when a user accesses this workflow, the table will ideally be populated with their files (`user_resources`).  This template expects that `user_resources` is iterable; each item (`resource`) should have `name`, `id`, and `human_readable_size` attributes.  *How* the able is populated is determined by a "handler" file.  In the section titled "Backend mapping", we described a different type of handler, which mapped the front-end inputs to the WDL inputs just prior to launching the workflow.  The handler in question here handles the population of the GUI in the first place.  

For the file chooser element discussed in this section, the `gui_schema.json` file provides a default handler at `<repository directory>/workflow_ingestion/default_handlers/file_chooser_handler.py` (see the `handler` parameter inside the `file_chooser` element).  If you choose to provide a different handler, you may specify that in your `gui.json`:
```
{
    "input_elements": [
        ...
        {
            "target": {
            "target_ids": ["TestWorkflow.inputs"],
            ...
            },
            "display_element": {
                "type": "file_chooser",
                ...
                "handler": "custom_handler.py",
                ...
            }	
        },
        ...
    ]
}
```
(The important line is the `handler` key *inside* the `display_element`)

  The only requirement for the handler is that it contains a function named `add_to_context` with the following signature:
```
def add_to_context(request, context_dict, context_args):
    ... code here...
```
The `request` argument is a Django request instance, which allows you to access the `request.user` field to identify the client (among other things).  The `context_dict` argument is a Python dictionary which provides the content for the HTML template.  The keys in that dictionary map directly to the template.  The final argument, `context_args` is another dictionary, which contains additional information used to customize the display.  A concrete example will make this clearer: 

```
import re

# simple class that acts as a "container" for sending file info to the front end:
class ResourceDisplay:
    ...
...

def add_to_context(request, context_dict, context_args):
    user = request.user
    r = Resource.objects.user_resources(user)
    display_resources = []
    filter = context_args['filter']
    for rr in r:
        if rr.is_active:
            m = re.match(filter, rr.name)
            if m and (m.group(0) == rr.name):
                display_resources.append(ResourceDisplay(rr.pk, rr.name, rr.size))
    context_dict['user_resources'] = display_resources

```
Here, we see that we first use the `request` argument to find out which user made the request and query the database for that user's files.  We then iterate through each of their files, performing the following checks:
- Ensure the file is "active"
- Check that the filename matches the expected regex pattern given by `filter`

If the file passes both of these checks, a `ResourceDisplay` object is added to a list (`display_resources`).  Finally, that list is added to the `context_dict`, addressed by the `user_resources` key, which we had declared in the HTML template.  `ResourceDisplay` is a simple "container" class defined in the same file and is helpful for sending content to the front-end.  It also has a method for taking the file's size (in bytes) and creating a "human-readable" string (e.g. 10.2MB).  As we saw in the HTML template, we require that the class has the `name`, `id`, and `human_readable_size` attributes to display properly.  For the full implementation, see `<repository dir>/workflow_ingestion/default_handlers/file_chooser_handler.py`.

Note that the `context_args` dictionary (which contained the key `filter` above) is declared in the `gui_schema.json` (obviously inside the portion describing the file chooser element):
```
...
    {
        "name": "context_args",
        "type": "mapping",
        "required": false,
        "default": {
            "filter": ".*"
        }
    }
...
```

As mentioned when discussing the population of the dropdown menu, the `"type": "mapping"` line is simply a cue, and does not enforce any particular data structure.  The default value prescribes mapping containing a single key (`filter`) which references a greedy regular expression.  Therefore, the file chooser will, by default, show all the user's files.  We can override this default by explicitly declaring the `context_args` key in our `gui.json`:
```
...
{
    "target": {
        "target_ids": ["ExomeWorkflow.normalSamples", "ExomeWorkflow.tumorSamples"],
        "name": "input_files",
        "handler": "input_mapping.py"
    },
    "display_element": {
        "type": "file_chooser",
        "context_args": {
            "filter":".*fastq.gz"
        },
        "label": "Input files:",
        "choose_multiple": true,
        "description": "Choose both tumor and normal samples for the analysis"
    }	
},
...
```
Here, the filter will only match filenames ending with "fastq.gz", and will thus only show Fastq-format sequencing files named accordingly.

One can include any number of additional keys in the `context_args` dictionary, and use those keys in the handler code to further customize the behavior of the file chooser.  For instance, one might specify
```
"context_args": {
    "filter":".*fastq.gz",
    "max_file_size": 5368709120
}
``` 
and use that `max_file_size` in the `add_to_context` function to limit the displayed files to those smaller than 5Gb. 

**In summary**
When creating a new input element, we advise that you start from a HTML interface that meets your needs and work backwards.  Decide the content that is 1) user-independent and 2) user-dependent, and then "templatize" the HTML in the manner similar to above.  Use the "raw" tags to "hide" the user-dependent template code on the first pass through templating.  Once that is complete, then you can begin to edit the `gui_schema.json` file to formally include this new element.  

To use the file-chooser example, we started with HTML which would display a table populated by file information (filename, file size).  We decided that the following parts of the table were user independent:
- label (string)
- description (string)
- choose_multiple (boolean, allowing selection of >1 files)
Therefore, we immediately included those in the `parameters` list for the file chooser.

Next, to properly display the user-dependent content (the files), we knew that we needed to have some "handler" code which provides data to the front-end in the expected format.  Thus, we included "handler" as a parameter and wrote a handler function that conformed to the defined specification (the required signature for `add_to_context` above).  Regardless of the logic contained therein, the handler needs to conform to that specification for the CNAP to understand and use it.  We also include the `context_args` to allow for additional customization.  Note that the key/value pairs inside `context_args` are closely tied to the handler code, and the handler code is tied to the HTML, so all the pieces of this new element are coupled.

Finally, we note that the file-chooser element defines an additional javascript file referenced by `js_handler`.  The javascript contained in that file performs the task of "preparing" the data to be sent to the backend in a POST request.  In the HTML at the beginning of this section, we had a checkbox given by:
```
 <input class="download-selector" type="checkbox" target="{{resource.id}}"/>
 ```
 When the user clicks "analyze" in the UI, the javascript referenced by `js_handler` looks through the file-chooser, parses out that `target` attribute (which is ultimately a primary key for a `Resource`), and constructs a list of primary keys which are sent to the backend.  Again, the `js_handler` javascript is *only* executed upon submission of the analysis, and is not used to add interactivity to the custom HTML.      


#### Styling

Much of the HTML elements provided with CNAP use CSS classes from the Bootstrap 4 framework.  If you wish to change the appearance, you may edit the HTML and/or the CSS file at `<repository dir>/workflow_ingestion/css/analysis_form.css`.

#### Hidden params

There are situations where a WDL developer might include inputs to the workflow that *should not* be arbitrarily customized, at least not without specialized knowledge.  An example might be setting a k-mer length (an integer) for an alignment algorithm.  When this WDL is integrated with the CNAP, it might be desired to fix that parameter and only allow specification of the remaining inputs.  

To ensure that we specify all the required inputs to the workflow, the `ingest_workflow.py` script checks the set of WDL inputs versus the set of inputs described in `gui.json`.  If the sets are not equivalent, an error is raised.  Thus, to fix a parameter (e.g. the k-mer length), we need a way to set an input element that "hides" the parameter from the client.  We use the standard HTML hidden element for this.  
At the time of writing, the hidden element only accepts a single value that maps to a single WDL input.  More complex hidden inputs can be constructed, but are not included by default.







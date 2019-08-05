/* 
******************************************************
START Loading of dynamic resources: 
******************************************************
*/

var csrfToken = getCookie('csrftoken');

// Get the active resources for the download tab:
function loadDownloads(){
$.ajax({
    url:"{{resource_tree_endpoint}}?include_uploads=false",
    type:"GET",
    headers:{"X-CSRFToken": csrfToken},
    success:function(response){
        $("#downloads-tree").treeview({
                data: response,
                multiSelect: true,
                showCheckbox: true,
                checkedIcon: "far fa-check-square",
                uncheckedIcon: "far fa-square",
                expandIcon: "far fa-plus-square",
                collapseIcon: "far fa-minus-square",
                showBorder: false,
                highlightSelected: false,
                levels: 1,
                searchResultColor: "#155724",
                searchResultBackColor:"#d4edda"
            });
            setupMethods("downloads-tree");
        if (response.length === 0)  {
            console.log('No downloads to display');
            //TODO: add html markup when table is empty
            $("#downloads-tree").html("<p class=\"alert alert-warning\">No files are available for download</p>");
        }
    },
    error:function(){
        console.log('error!');
    }
});
}
loadDownloads();

// get available analyses/workflows:
$.ajax({
    url:"{{analysis_list_endpoint}}?completed=false&gui=true",
    type:"GET",
    headers:{"X-CSRFToken": csrfToken},
    success:function(response){
        var analysisTable = $("#analysis-table tbody");
        var markup = "";
        if (response.length > 0){
            for(var i=0; i<response.length; i++){
                var workflow_obj = response[i]['workflow'];
                var title = workflow_obj['workflow_title'];
                var short_description = workflow_obj['workflow_short_description'];

                var analysis_uuid = response[i]['analysis_uuid'];
                markup += `<tr>
                      <td><a target="_blank" class="analysisLink" href="{{analysis_project_endpoint}}${analysis_uuid}/">${title} <i style="font-size:16px" class="fa fa-external-link-alt"></i></a></td>
                      <td>${short_description}</td>
                    </tr>`;
            }
        } else {
            markup = `<tr><td colspan="2" align="center">No analysis projects have been created for this user.  Contact the administrator to set one up.</td></tr>`
        }
        analysisTable.append(markup); 

    },
    error:function(){
        console.log('error!');
    }
});

function parseDateString(s){
    // string is formatted like:
    //  YYYY-MM-DDTHH:MM:SS.XXXXXXZ
    if (s !== null){
        var contents = s.split("T");
        return contents[0];
    } else {
        return "-";
    }
}

function parseDurationString(s){
    // string is formatted like "D HH:MM:SS"
    // where D is integer  (representing days)
    // and is NOT there if D=0 (e.g. only "HH:MM:SS") 
    // if less than 1 day
    var contents = s.split(" ");
    if(contents.length == 2){
        var day = parseInt(contents[0]);
        var time_contents = contents[1].split(":");
        var hours = parseInt(time_contents[0]);
        var totalHours = 24*day + hours;
        var minutes = time_contents[1]; //not parsing as int keeps zero padding
        var seconds_incl_ms = time_contents[2].split('.'); //not parsing as int keeps zero padding
        var seconds = seconds_incl_ms[0];
        return `${totalHours}:${minutes}:${seconds}`;
    }else{
        var time_contents = s.split(":");
        var hours = time_contents[0];
        var minutes = time_contents[1]; //not parsing as int keeps zero padding
        var seconds_incl_ms = time_contents[2].split('.'); //not parsing as int keeps zero padding
        var seconds = seconds_incl_ms[0];
        return `${hours}:${minutes}:${seconds}`;
    }
}

function showTransferDetail(pk){
    var item = transfer_history[pk];
    var filename = item['resource']['name'];
    var startTime = parseDateString(item['start_time']);
    var direction = item['download'] ? "Download" : "Upload";
    var destination = "-";
    if(item['download']){
        destination = item['destination']
    }

    var completed = item['completed'];
    var completedSymbol = completed ? "&#10004;" :"&#x2716;";
    var success = "-";
    var successSymbol = "-";
    var duration = "-";
    if(completed){
        success = item['success'];
        if(success){
            successSymbol = "&#10004;";
            duration = parseDurationString(item['duration']);
        }else{
            successSymbol = "&#x2716;"
        }
    }

    // compose the table content:
    var markup = ""
    markup += `<tr><td>Filename</td><td>${filename}</td></tr>`;
    markup += `<tr><td>Type</td><td>${direction}</td></tr>`;
    markup += `<tr><td>Date</td><td>${startTime}</td></tr>`;
    markup += `<tr><td>Duration</td><td>${duration}</td></tr>`;
    markup += `<tr><td>Destination</td><td>${destination}</td></tr>`;
    markup += `<tr><td>Completed</td><td>${completedSymbol}</td></tr>`;
    markup += `<tr><td>Success</td><td>${successSymbol}</td></tr>`;
    $("#history-detail-table tbody").empty().append(markup);

    //hide other content:
    $(".subcontent").hide();
    $("#history-detail-section").show();
}

function showAnalysisHistoryDetail(pk){
    var item = analysis_history[pk];
    console.log(item);
    var workflow_title = item['workflow']['workflow_title'];
    var workflow_version = item['workflow']['version_id'];
    var workflow_description = item['workflow']['workflow_long_description'];

    var startTime = parseDateString(item['start_time']);
    var status = item['status'];

    var completed = item['completed'];
    var completedSymbol = completed ? "&#10004;" :"&#x2716;";
    var success = "-";
    var successSymbol = "-";
    var finishTime = "-";
    if(completed){
        success = item['success'];
        finishTime = parseDateString(item['finish_time']);
        if(success){
            successSymbol = "&#10004;";
        }else{
            successSymbol = "&#x2716;"
        }
    }

    // compose the table content:
    var markup = ""
    markup += `<tr><td>Workflow</td><td>${workflow_title}</td></tr>`;
    markup += `<tr><td>Workflow version</td><td>${workflow_version}</td></tr>`;
    markup += `<tr><td>Workflow description</td><td>${workflow_description}</td></tr>`;
    markup += `<tr><td>Status</td><td>${status}</td></tr>`;
    markup += `<tr><td>Start time</td><td>${startTime}</td></tr>`;
    markup += `<tr><td>Finish time</td><td>${finishTime}</td></tr>`;
    markup += `<tr><td>Completed</td><td>${completedSymbol}</td></tr>`;
    markup += `<tr><td>Success</td><td>${successSymbol}</td></tr>`;
    $("#history-detail-table tbody").empty().append(markup);

    //hide other content:
    $(".subcontent").hide();
    $("#history-detail-section").show();
}

// need these in the global scope
var transfer_history = {};
var analysis_history = {};

// get the history
get_history = function(){

    $.ajax({
        url:"{{transferred_resources_endpoint}}",
        type:"GET",
        headers:{"X-CSRFToken": csrfToken},
        success:function(response){
            var tableBody = $("#transfer-history-table tbody");
            var markup = "";
            if (response.length > 0 ){
                for(var i=0; i<response.length; i++){
                    var item = response[i];
                    var pk = item['id'];
                    transfer_history[pk] = item;
                    var filename = item['resource']['name'];
                    markup += `<tr>
                      <td>${filename}</td>
                      <td><span class="detail-loader" detail-key="${pk}">View</span></td>
                    </tr>`;
                }
            }
            else {
                markup = `<tr><td colspan="2" align="center">No transfer history to show</td></tr>`
            }
            tableBody.empty().append(markup);

            $(".detail-loader").click(function(e){
                e.preventDefault();
                var targetedDetail = $(this).attr("detail-key");
                showTransferDetail(targetedDetail);
            });
        },
        error:function(){
            console.log('error!');
        }
    });

    $.ajax({
        url:"{{analysis_list_endpoint}}?started=true",
        type:"GET",
        headers:{"X-CSRFToken": csrfToken},
        success:function(response){
            var tableBody = $("#analysis-history-table tbody");
            var markup = "";
            if (response.length > 0 ){
                for(var i=0; i<response.length; i++){
                    var item = response[i];
                    var uuid = item['analysis_uuid'];
                    var pk = item['id'];
                    analysis_history[pk] = item;
                    var analysis_name = item['workflow']['workflow_title'];
                    markup += `<tr>
                      <td>${analysis_name}</td>
                      <td><span class="detail-loader" detail-key="${pk}">View</span></td>
                    </tr>`;
                }
            }
            else {
                markup = `<tr><td colspan="2" align="center">No analysis history to show</td></tr>`
            }
            tableBody.empty().append(markup);

            $(".detail-loader").click(function(e){
                e.preventDefault();
                var targetedDetail = $(this).attr("detail-key");
                showAnalysisHistoryDetail(targetedDetail);
            });
        },
        error:function(){
            console.log('error!');
        }
    });

}

get_history();

// a function to call if the user would like to view their current files
function showCurrentFiles(){
    console.log('GO GET FILES');
    $.ajax({
        url:"{{resource_tree_endpoint}}?include_uploads=true",
        type:"GET",
        headers:{"X-CSRFToken": csrfToken},
        success:function(response){
            $("#current-files-tree").treeview({
                    data: response,
                    multiSelect: true,
                    showCheckbox: true,
                    checkedIcon: "far fa-check-square",
                    uncheckedIcon: "far fa-square",
                    expandIcon: "far fa-plus-square",
                    collapseIcon: "far fa-minus-square",
                    showBorder: false,
                    highlightSelected: false,
                    levels: 1,
                    searchResultColor: "#155724",
                    searchResultBackColor:"#d4edda"
                });
                setupMethods("current-files-tree");
            if (response.length === 0)  {
                console.log('No files to display');
                //TODO: add html markup when table is empty
                $("#current-files-tree").html("<p class=\"alert alert-warning\">No files are associated with this user account.</p>");
            }
        },
        error:function(){
            console.log('error!');
        }
    });
}
showCurrentFiles();
/* 
******************************************************
END Loading of dynamic resources
******************************************************
*/



/* 
******************************************************
START Dropbox JS 
******************************************************
*/

// Below is code related to the chooser provided by Dropbox:
var dbxOptions = {

    // Required. Called when a user selects an item in the Chooser.
    success: function(files) {
        var data = [];
        for( var i=0; i < files.length; i++){
            var f = files[i];
            data.push({"source_path":f.link, "name":f.name, "size_in_bytes":f.bytes});
        }

        $.ajax({
            url:"{{upload_url}}",
            method:"POST",
            data: {"upload_source":"Dropbox", "upload_info": JSON.stringify(data)},
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                console.log('Upload started.');
		showGeneralDialog('Your upload from Dropbox has started.');
            },
            error:function(){
                console.log('Error.');
            }
        });
    },

    // Optional. Called when the user closes the dialog without selecting a file
    // and does not include any parameters.
    cancel: function() {

    },

    // Optional. "preview" (default) is a preview link to the document for sharing,
    // "direct" is an expiring link to download the contents of the file. For more
    // information about link types, see Link types below.
    linkType: "direct",

    // Optional. A value of false (default) limits selection to a single file, while
    // true enables multiple file selection.
    multiselect: true,
};

$("#dropbox-upload").click(function(e){
    Dropbox.choose(options);
});
// end code regarding chooser

/*
******************************************************
END Dropbox JS 
******************************************************
*/




/*
******************************************************
 START Google Drive JS 
******************************************************
*/

// The Browser API key obtained from the Google API Console.
// Replace with your own Browser API key, or your own key.
var developerKey = "{{drive_api_key}}";

// The Client ID obtained from the Google API Console. Replace with your own Client ID.
var clientId = "{{drive_client_id}}"

// Replace with your own project number from console.developers.google.com.
// See "Project number" under "IAM & Admin" > "Settings"
var appId = "{{google_project_number}}";

// Scope to use to access user's Drive items.
var scope = ["{{drive_scope}}"];

var pickerApiLoaded = false;
var oauthToken;

// Use the Google API Loader script to load the google.picker script.
function loadPicker() {
    gapi.load('auth', {'callback': onAuthApiLoad});
    gapi.load('picker', {'callback': onPickerApiLoad});
}

function onAuthApiLoad() {
    window.gapi.auth.authorize(
        {
            'client_id': clientId,
            'scope': scope,
            'immediate': false
        },
        handleAuthResult
    );
}

function onPickerApiLoad() {
    pickerApiLoaded = true;
    createPicker();
}

function handleAuthResult(authResult) {
    if (authResult && !authResult.error) {
        oauthToken = authResult.access_token;
        createPicker();
    }
}

// Create and render a Picker object for searching images.
function createPicker() {
    if (pickerApiLoaded && oauthToken) {

        // view all of Drive
        var view = new google.picker.View(google.picker.ViewId.DOCS);
        var picker = new google.picker.PickerBuilder()
            .enableFeature(google.picker.Feature.NAV_HIDDEN)
            .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
            .setAppId(appId)
            .setOAuthToken(oauthToken)
            .addView(view)
            .setDeveloperKey(developerKey)
            .setCallback(pickerCallback)
            .build();
        picker.setVisible(true);
    }
}

// A simple callback implementation.
function pickerCallback(data) {
    if (data.action == google.picker.Action.PICKED) {
        var d = [];
        for( var i=0; i < data.docs.length; i++){
            var f = data.docs[i];
            d.push({"file_id":f.id, "name":f.name, "size_in_bytes":f.sizeBytes, "drive_token": oauthToken});
        }

        $.ajax({
            url:"{{upload_url}}",
            method:"POST",
            data: {"upload_source":"Google Drive", "upload_info": JSON.stringify(d)},
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                console.log('Upload started.');
		showGeneralDialog('Your upload from Google Drive has started.');
            },
            error:function(){
                console.log('Error.');
            }
        });
    }
}

/* 
******************************************************
END Google Drive JS
******************************************************
 */




$(".section-chooser").click(function(){
    // remove class from siblings:
    var sibs = $(this).siblings();
    for(var i=0; i<sibs.length; i++){
        $(sibs[i]).removeClass("selected");
    }
    // add selected class to this
    $(this).addClass("selected");

    // make some adjustments to borders around the tabs
    if ($(this).is(":first-child")){
        $(this).addClass("first-tab");
    }
     if ($(this).is(":last-child")){
        $(this).addClass("last-tab");
    }

    //hide other content:
    $(".subcontent").hide();

    // show the content:
    var content_target = $(this).attr("content-target");
    var element = $("#" + content_target);
    $(element).toggle();

    $("#current-files-tree").empty();
    showCurrentFiles();

    $("#downloads-tree").empty();
    loadDownloads();
})

$("#refresh-history").click(function(){
    get_history();
});


$("#back-to-history").click(function(){
    get_history();
    $("#history-detail-section").toggle();
    $("#history").toggle();
});


showGeneralDialog = function(message){
     var dialog = $("#general-dialog");
     var subdiv = $("#dialog-content")
     var markup = "<div>"+ message +"</div>"
     subdiv.empty().append(markup);
     $("#wrapper").toggleClass("blur");
     dialog.toggle();
}
 
$("#close-general-dialog").click(function(){
     $("#wrapper").toggleClass("blur");
     $("#general-dialog").toggle();
});


showErrorDialog = function(obj_array){
     console.log('show dialog');
     console.log(obj_array);
     var dialog = $("#error-dialog");
     var subdiv = $("#error-dialog-list")
     var markup = "";
     for(var i=0; i<obj_array.length; i++){
         markup += "<p>"+ obj_array[i] +"</p>"
     }
     subdiv.empty().append(markup);
     $("#wrapper").toggleClass("blur");
     dialog.toggle();
}
 
$("#close-error-dialog").click(function(){
     $("#wrapper").toggleClass("blur");
     $("#error-dialog").toggle();
});


// Below is code related to javascript for downloads.  When the user clicks on the button
// JS needs to collect the info about what to send. 

$(".init-download-btn").click(function(){
    // get the selections from the download tree:
    var selected = $("#downloads-tree").treeview('getSelected');
    console.log('selected: '  + JSON.stringify(selected));
    
    if(selected.length > 0){
        var destination = $(this).attr("destination");
        var selectedPks = [];
        for(var i in selected){
            var pk = selected[i].pk;
            selectedPks.push(pk);
        }
        var data = {"resource_pks": selectedPks, "destination":destination};
        var payload = {"data":JSON.stringify(data)};
        $.ajax({
            url:"{{download_url}}",
            method:"POST",
            dataType: "json",
            data: payload,
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                window.open("https://"+ window.location.hostname + (window.location.port ? ':' + window.location.port: '')+ "{{download_url}}", "newWindow", "width=800,height=600");
            },
            error:function(response){
                console.log('Error.');
                var jsonResponse = response['responseJSON'];
                showErrorDialog(jsonResponse['errors']);
            }
        });
    }else{
        showErrorDialog(["You must select a resource to download first."]);
        console.log("Nothing to do- no resources selected.");
    }

});

// End code related to javascript for downloads

// Below is code related to javascript for uploads

$(".init-upload-btn").click(function(){
    var uploadSource = $(this).attr("upload-source");
    if(uploadSource == 'Dropbox'){
        Dropbox.choose(dbxOptions);
    } else if(uploadSource == 'Google Drive'){
        loadPicker();
    }
});

//End code related to javascript for uploads

showConfirmationDialog = function(message){
     var dialog = $("#confirmation-dialog");
     var subdiv = $("#confirmation-dialog-content")
     var markup = "<div>"+ message +"</div>"
     subdiv.empty().append(markup);
     $("#wrapper").toggleClass("blur");
     dialog.toggle();
}

var confirmation_actions = {'confirm': null, 'cancel': null};


$("#confirm-action-button").click(function(){
     console.log('DO IT!');
     confirmation_actions['confirm']();
     $("#wrapper").toggleClass("blur");
     $("#confirmation-dialog").toggle();
});

$("#cancel-action-button").click(function(){
     console.log('cancel');
     $("#wrapper").toggleClass("blur");
     $("#confirmation-dialog").toggle();
});


function performDeletions(pk_list){

    var count = pk_list.length;
    var all_done = $.Deferred();

    for(var i in pk_list){
        var pk = pk_list[i];
        $.ajax({
            url:"/resources/" + pk,
            method:"DELETE",
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                console.log('deleted!');
                count--;
                if(count === 0){
                    all_done.resolve();
                }
            },
            error:function(response){
                console.log('Error with deletion.');
                var jsonResponse = response['responseJSON'];
                showErrorDialog(jsonResponse['errors']);
            }
        });
    }
    return all_done.promise();
}


deleteFiles = function(pk_list){
    $("#current-files-tree").empty();
    performDeletions(pk_list).done(
        function(){
            showCurrentFiles();
        }
    );
}


$("#delete-files").click(function(){

    var selected = $("#current-files-tree").treeview('getSelected');
    var selectedPks = [];
    for(var i in selected){
        var pk = selected[i].pk;
        if(pk !== undefined){
            selectedPks.push(pk);
        }
    }
    if(selectedPks.length > 0){
        var confirm_delete_action = function(pks){
            var pkList=pks;
            return function(){
		deleteFiles(pkList);
            }
        }(selectedPks);

        confirmation_actions['confirm'] = confirm_delete_action;
        message = 'You have selected ' + selectedPks.length  + ' file(s) for deletion.  This action will permanently delete files from our system.  Please confirm this action.';
        showConfirmationDialog(message);
    } else {
        showErrorDialog(["You have not selected any files to delete."]);
    }
});

function generateRenamingMarkup(pk_list, original_namelist, element_id){
    // pk_list has the primary keys of the resources
    // original_namelist has the names of those files as they were.  These
    // will be put into textboxes for the user to edit
    // returns html markup which will be inserted into a div
    var markup = `<div id="${element_id}">`;
    markup += '<p>Rename the files below.  Note that if the </p>'
    for(var i in pk_list){
        var pk = pk_list[i];
        var name = original_namelist[i];
        markup += `<input type="text" pk=${pk} value=${name} class="form-control file-rename">`;
    }
    markup += "</div>";
    return markup;
}


function performRename(pk_list, name_list){

    var count = pk_list.length;
    var all_done = $.Deferred();

    for(var i in pk_list){
        var pk = pk_list[i];
        var newname = name_list[i];
        var payload = {"new_name":newname};
        $.ajax({
            url:"{{resource_rename_endpoint}}" + pk + "/",
            method:"POST",
            data: payload,
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                console.log('renamed!');
                count--;
                if(count === 0){
                    all_done.resolve();
                }
            },
            error:function(response){
                console.log('Error with rename.');
                console.log(response);
                //var jsonResponse = response['responseJSON'];
                //showErrorDialog(jsonResponse['errors']);
                showErrorDialog(['Could not rename this.', 'Could not rename that either']);
            }
        });
    }
    return all_done.promise();
}


function do_rename(pk_list, elementID){
    var children = $("#" + elementID).children("input");
    var name_list = [];
    for(var c=0; c<children.length; c++){
        var child = children[c];
        var val = $(child).val();
        name_list.push(val);
        console.log('pk=' + pk_list[c] + ", new name=" + val);
    }
    performRename(pk_list, name_list).done(
        function(){
            showCurrentFiles();
        }
    );
}

$("#rename-files").click(function(){

    var selected = $("#current-files-tree").treeview('getSelected');
    var selectedPks = [];
    var selectedFilenames = [];
    for(var i in selected){
        var pk = selected[i].pk;
        var filename = selected[i].filename;
        if((pk !== undefined) & (filename !== undefined)){
            selectedPks.push(pk);
            selectedFilenames.push(filename);
        }
    }
    if(selectedPks.length > 0){
        console.log('Change names of:');
        console.log(selectedFilenames);
        var elementID = "file-renaming-section"; //used for identifying the area in the dialog where the user will enter the new filenames
        var confirm_rename_action = function(pks, element_id){
            return function(){
		do_rename(pks, element_id);
            }
        }(selectedPks, elementID);

        confirmation_actions['confirm'] = confirm_rename_action;
        content = generateRenamingMarkup(selectedPks, selectedFilenames, elementID);
        showConfirmationDialog(content);
    } else {
        showErrorDialog(["You have not selected any files to rename."]);
    }
});

$("#current-files-refresh").click(function(){
    $("#current-files-tree").empty();
    showCurrentFiles();
});

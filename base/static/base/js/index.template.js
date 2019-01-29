// function to print human-readable file size
function humanFileSize(bytes) {
    var thresh = 1024;
    if(Math.abs(bytes) < thresh) {
        return bytes + ' B';
    }
    var units = ['kB','MB','GB','TB','PB'];
    var u = -1;
    do {
        bytes /= thresh;
        ++u;
    } while(Math.abs(bytes) >= thresh && u < units.length - 1);
    return bytes.toFixed(1)+' '+units[u];
}

/* 
******************************************************
START Loading of dynamic resources: 
******************************************************
*/

var csrfToken = getCookie('csrftoken');

// Get the active resources for the download tab:
$.ajax({
    url:"{{resource_endpoint}}?is_active=true",
    type:"GET",
    headers:{"X-CSRFToken": csrfToken},
    success:function(response){
        var tableBody = $("#download-table tbody");
        var markup = "";
        if (response.length > 0){
            for(var i=0; i<response.length; i++){
                var item = response[i];
                var size = humanFileSize(item['size']);
                var filename = item['name'];
                markup += `<tr>
                      <td><input class="download-selector" type="checkbox" target="${item['id']}"/></td>
                      <td>${filename}</td>
                      <td>${size}</td>
                    </tr>`;
            }
        } else {
            markup = `<tr><td colspan="2" align="center">No resources to download</td></tr>`
        }
        tableBody.append(markup); 
    },
    error:function(){
        console.log('error!');
    }
});

// get available analyses/workflows:
$.ajax({
    url:"{{analysis_list_endpoint}}",
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
                      <td><a target="_blank" class="analysisLink" href="{{analysis_project_endpoint}}${analysis_uuid}/">${title} <i style="font-size:16px" class="fa">&#xf08e;</i></a></td>
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
    var contents = s.split("T");
    return contents[0];
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

function showDetail(pk){
    var item = history[pk];
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

// need this in the global scope
var history = {};

// get the history
get_history = function(){
    $.ajax({
        url:"{{transferred_resources_endpoint}}",
        type:"GET",
        headers:{"X-CSRFToken": csrfToken},
        success:function(response){
            var tableBody = $("#history-table tbody");
            var markup = "";
            if (response.length > 0 ){
                for(var i=0; i<response.length; i++){
                    var item = response[i];
                    var pk = item['id'];
                    history[pk] = item;
                    var filename = item['resource']['name'];
                    markup += `<tr>
                      <td>${filename}</td>
                      <td><span class="detail-loader" detail-key="${pk}">View</span></td>
                    </tr>`;
                }
            }
            else {
                markup = `<tr><td colspan="2" align="center">No user history to show</td></tr>`
            }
            tableBody.empty().append(markup);

            $(".detail-loader").click(function(e){
                e.preventDefault();
                var targetedDetail = $(this).attr("detail-key");
                showDetail(targetedDetail);
            });
        },
        error:function(){
            console.log('error!');
        }
    });
}

get_history();

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
            data.push({"path":f.link, "name":f.name, "size_in_bytes":f.bytes});
        }

        $.ajax({
            url:"{{upload_url}}",
            method:"POST",
            data: {"upload_source":"Dropbox", "upload_info": JSON.stringify(data)},
            headers:{"X-CSRFToken": csrfToken},
            success:function(response){
                console.log('Upload started.');
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
})

$("#refresh-history").click(function(){
    get_history();
});


$("#back-to-history").click(function(){
    get_history();
    $("#history-detail-section").toggle();
    $("#history").toggle();
});


// Below is code related to javascript for downloads.  When the user clicks on the button
// JS needs to collect the info about what to send. 

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

$(".init-download-btn").click(function(){
    var selectedPks = [];
    var checkBoxes = $("#download-table tbody").find(".download-selector");
    for( var i=0; i<checkBoxes.length; i++ ){
        var cbx = checkBoxes[i];
        if($(cbx).prop("checked") == true){
            selectedPks.push($(cbx).attr("target"));
        }
    }
    if(selectedPks.length > 0){
        var destination = $(this).attr("destination");
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
    if(uploadSource == '{{dropbox}}'){
        Dropbox.choose(dbxOptions);
    } else if(uploadSource == '{{google_drive}}'){
        loadPicker();
    }
});

//End code related to javascript for uploads


var form_problems = [];

// code for showing errors on form:
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


var prepareFormData = function(){

    // We declare two variables-- 
    // payload is an object that holds the data we will eventuall
    // send to the backend
    var payload = {};

    // The other variable is the form itself:
    var analysisForm = $("#analysis-creation-form");

    // javascript for customized input elements will go here:
    
                var el = $("#text-0");
        var dataTarget = $(el).attr("dataTarget");

        if(!el[0].checkValidity()){
            form_problems.push("There was an empty text field.");
            return;
        }
        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            
                var pattern1 = /\s+/g;
                val = val.replace(pattern1, '_');
                var pattern2 = /^[\-_a-zA-Z0-9]+$/;
                if (!val.match(pattern2) && val.length > 0 ){
                    form_problems.push("The value of \""+ val  +"\" was unexpected.  Please enter a value with only letters, numbers, underscores (\"_\"), and dashes (\"-\")");
                    return;
                }
            
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }
    
                var el = $("#text-1");
        var dataTarget = $(el).attr("dataTarget");

        if(!el[0].checkValidity()){
            form_problems.push("There was an empty text field.");
            return;
        }
        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            
                var pattern1 = /\s+/g;
                val = val.replace(pattern1, '_');
                var pattern2 = /^[\-_a-zA-Z0-9]+$/;
                if (!val.match(pattern2) && val.length > 0 ){
                    form_problems.push("The value of \""+ val  +"\" was unexpected.  Please enter a value with only letters, numbers, underscores (\"_\"), and dashes (\"-\")");
                    return;
                }
            
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }
    

    return payload;
}

function create_post(payload){
    var url = $("#analysis-creation-form").attr("submit_url");
    $.ajax({
            url: url,
            type: "post",
            data: {"data": JSON.stringify(payload)},
            //data: payload,
            success: function(response){
                console.log('Success!');

                // if this was a test-case, simply clear the contents 
                // of the UI, and show the inputs.json result
                if (response.hasOwnProperty("test")){
                    var json = response["message"];
                    var markup = `<p>The final inputs.json file would be: </p><pre>${json}</pre>`
                    $("#main-container").empty().append(markup);
                } else {
                    // reload the page, which will show the job status
                    window.location.href = window.location.href;
                }

            },
            error: function(xhr, status, err){
                console.log('Error!');
                if (xhr.status === 403){
                    alert("You may not perform this action.  Do you own this project?");
                } else {
                    alert("There was a problem submitting the analysis.  If you believe this is in error, please contact the administrators.");
                }
            }

    });
}


$("#submit-form").click(function(e){
    e.preventDefault();
    form_problems = [];
    var data = prepareFormData();
    if(data===undefined){
        console.log('Problem with form');
        showErrorDialog(form_problems);
    } else {
        create_post(data);
    }
});
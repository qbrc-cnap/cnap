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
    {% for handler_code in submit_handlers %}
        {{handler_code}}
    {% endfor %}

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

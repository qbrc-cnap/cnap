var prepareFormData = function(){

    // We declare two variables-- 
    // payload is an object that holds the data we will eventuall
    // send to the backend
    var payload = {};

    // The other variable is the form itself:
    var analysisForm = $("#analysis-creation-form");

    // javascript for customized input elements will go here:
    {% for handler_code in js_handlers %}
        {{handler_code}}
    {% endfor %}

    return payload;
}

function create_post(payload){
    var url = $("#analysis-creation-form").attr("action");
    $.ajax({
            url: url,
            type: "post",
            data: {"data": JSON.stringify(payload)},
            //data: payload,
            success: function(response){
                console.log('Success!');

                // reload the page, which will show the job status
                window.location.href = window.location.href;
            },
            error: function(xhr, status, err){
                console.log('Error!');
            }

    });
}


$("#submit-form").click(function(e){
    e.preventDefault();
    var data = prepareFormData();
    create_post(data);
});

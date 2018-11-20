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

    // select native input elements that are part of the form
    var elements = $(analysisForm).find("input, select");
    for(var i=0; i<elements.length; i++){
        var el = $(elements[i]);
        var dataTarget = el.attr("dataTarget");
        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }
    }
    return payload;
}

function create_post(payload){
    console.log(payload)
}

$("#submit-form").click(function(e){
    e.preventDefault();
    var data = prepareFormData();
    create_post(data);
});

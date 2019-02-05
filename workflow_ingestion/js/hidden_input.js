// This javascript works with the file_chooser.html interface
// This code will be placed inside a function where there exists
// a jQuery object named `analysisForm` and a plain object
// named `payload`, which is the data the form will send to the backend

var getHiddenInputs = function (form){

    // get all the elements that have "input_radio" as an attribute
    var element_array = $(form).find("[input_hidden]");

    // declare a regular object to hold the data
    // we will send to backend
    var obj = {};

    for(var i=0; i<element_array.length; i++){
        var el = $(element_array[i]);
        var dataTarget = $(el).attr("dataTarget");

        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            obj[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }
    }
    return obj;
};

payload = Object.assign({}, payload, getHiddenInputs(analysisForm));

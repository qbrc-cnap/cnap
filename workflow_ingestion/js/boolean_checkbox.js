// This javascript works with the file_chooser.html interface
// This code will be placed inside a function where there exists
// a jQuery object named `analysisForm` and a plain object
// named `payload`, which is the data the form will send to the backend

var makeBoolean = function (form){

    // get all the checkboxes that have "boolean_checkbox" as an attribute
    var checkbox_array = $(form).find("[boolean_checkbox]");

    // declare a regular object to hold the data
    // we will send to backend
    var obj = {};

    for(var i=0; i<checkbox_array.length; i++){
        var cbx = $(checkbox_array[i]);
        var dataTarget = $(cbx).attr("dataTarget");

        //check if checked:
        if ($(cbx).prop("checked") == true){
            obj[dataTarget] = true;
        } else {
            obj[dataTarget] = false;
        }
    }
    return obj;
};

payload = Object.assign({}, payload, makeBoolean(analysisForm));

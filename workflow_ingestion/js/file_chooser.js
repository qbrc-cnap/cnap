// This javascript works with the file_chooser.html interface
// This code will be placed inside a function where there exists
// a jQuery object named `analysisForm` and a plain object
// named `payload`, which is the data the form will send to the backend

var fileChooserFunc = function (form){

    // get all file chooser tables inside form 
    var table_array = $(form).find(".custom-table");

    // declare a regular object to hold the data
    // we will send to backend
    var obj = {};

    // loop through, collect the primary keys
    for(var i=0; i<table_array.length; i++){
        var tbl = $(table_array[i]); //now have a table
        var dataTarget = $(tbl).attr("dataTarget");
        var selectedPks = [];
        var checkBoxes = $(tbl).find(".download-selector");
        for( var i=0; i<checkBoxes.length; i++ ){
            var cbx = checkBoxes[i];
            if($(cbx).prop("checked") == true){
                selectedPks.push($(cbx).attr("target"));
            }
        }
        if(selectedPks.length > 0){
            obj[dataTarget] = selectedPks;
        }else{
            console.log("Nothing to do- no resources selected.");
        }

    }
    return obj;
};

payload = Object.assign({}, payload, fileChooserFunc(analysisForm));

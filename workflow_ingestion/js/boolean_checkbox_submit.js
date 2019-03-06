    // grab the checkbox
    var cbx = $("#checkbox-{{id}}");
    var dataTarget = $(cbx).attr("dataTarget");

    //check if checked:
    if ($(cbx).prop("checked") == true){
        payload[dataTarget] = true;
    } else {
        payload[dataTarget] = false;
    }

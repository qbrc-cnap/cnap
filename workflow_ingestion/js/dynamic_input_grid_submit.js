    var dataTarget = $("#dynamic-input-grid-{{id}}").attr("dataTarget"); 
    var items = $("#dynamic-input-grid-{{id}} .dynamic-grid-input-row");

    // pre-allocate the result data structure:
    var grid_data = {};

    for(var i=0; i < items.length; i++){
        var div_item = items[i];
        var row_num = $(div_item).attr("row");
        var input_kid = $(div_item).children("input[column_index]")[0];
        var col = $(input_kid).attr("column_index");
        if(row_num in grid_data){
            grid_data[row_num][col] = input_kid.value;
        } else {
            grid_data[row_num] = {};
            grid_data[row_num][col] = input_kid.value;
        }
    }
    payload[dataTarget] = grid_data;
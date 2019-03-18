remove_row = function(e){
    var element = e.target;
    var row_index = $(element).attr("rmTarget");
    $(".dynamic-grid-input-row[row='"+ row_index +"']").remove();
}

var row_index_{{id}} = 0; // for enforcing a unique ID
var column_objs_{{id}} = $("#dynamic-input-grid-{{id}} .dynamic-grid-col");
var col_count_{{id}} = column_objs_{{id}}.length;
$("#add-row_{{id}}").click(function(e){
    row_index_{{id}} += 1;
    // handle all columns except last
    for(var i=0; i < (col_count_{{id}}-1); i++){
        var new_element = `<div class="dynamic-grid-input-row" row="${ row_index_{{id}} }">
            <input column_index="${i}" type="text">
            </div>`;
        var current_col = column_objs_{{id}}[i];
        $(current_col).append(new_element);
    }
    // handle last column which includes a 'remove' button
    var new_element = `<div class="dynamic-grid-input-row" row="${ row_index_{{id}} }">
            <input column_index="${col_count_{{id}}-1}" type="text"><i class="fas fa-times remove-dynamic-input-grid-row" rmTarget="${row_index_{{id}}}"></i></div>`;
        var current_col = column_objs[col_count_{{id}}-1];
        $(current_col).append(new_element);
        $(".remove-dynamic-input-grid-row").click(remove_row);
});
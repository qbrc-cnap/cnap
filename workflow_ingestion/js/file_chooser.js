var csrfToken = getCookie('csrftoken');


// for tracking which items are highlighted in the tree
var highlighted_items_{{id}} = [];

// jQuery object for the tree
var tree_{{id}} = $("#file-choice-tree-{{id}}");

function attach_functions_tree_{{id}}(){
// register method to run when the search is done
tree_{{id}}.on('searchComplete', function(event, data) {
    console.log("searchComplete!!!!!!!!!!!: " + JSON.stringify(data));
    highlighted_items_{{id}} = [];
    for(var item in data){
        highlighted_items_{{id}}.push(data[item].nodeId);
    }
    console.log('HLI: ' + JSON.stringify(highlighted_items_{{id}}));
});

// This lets us know which items were "unhighlighted" following a new search
tree_{{id}}.on('searchCleared', function(event, data){
    console.log("searchCleared: " + JSON.stringify(data));
    var allParents = new Set();
    for(var item in data){
            console.log('cleared:' + item);
            var parent = data[item].parentId;
                    console.log(parent);
            if (parent !== undefined){
                    allParents.add(parent);
            }
    }
    console.log('parent set:' + allParents);
    allParents.forEach(
            function(values){
                    console.log('val: ' + values);
                    tree_{{id}}.treeview('collapseNode', values);
            }
    );
});

// This allows us to check children by checking the parent node
tree_{{id}}.on('nodeChecked', function(event, node){
    var children = node.nodes;
    for(item in children){
        console.log(item);
        var nodeId = children[item].nodeId;
        tree_{{id}}.treeview('checkNode', nodeId);
        tree_{{id}}.treeview('selectNode', nodeId);
    }
    tree_{{id}}.treeview('expandNode', node.nodeId);
    tree_{{id}}.treeview('selectNode', node.nodeId);
});

// This allows us to uncheck all the children by unclicking the parent
tree_{{id}}.on('nodeUnchecked', function(event, node){
    //get any children and uncheck them as well.  Note only goes down ONE layer.
    var children = node.nodes;
    for(item in children){
        console.log(item);
        var nodeId = children[item].nodeId;
        tree_{{id}}.treeview('uncheckNode', nodeId);
        tree_{{id}}.treeview('unselectNode', nodeId);
    }
    tree_{{id}}.treeview('collapseNode', node.nodeId);
    tree_{{id}}.treeview('unselectNode', node.nodeId);
});

$("#select-highlighted-checkbox-{{id}}").change(function(e) {
    console.log('clicked!');
    console.log("CT: " +JSON.stringify(tree_{{id}}));
    if(this.checked){
            console.log('was checked');
            for(var i=0; i < highlighted_items_{{id}}.length; i++){
                tree_{{id}}.treeview('checkNode', highlighted_items_{{id}}[i]);
                tree_{{id}}.treeview('selectNode', highlighted_items_{{id}}[i]);
            }
            var selectedNodes = tree_{{id}}.treeview('getSelected');
            console.log(selectedNodes)
    } else {
            console.log('was unchecked');
            for(var i=0; i < highlighted_items_{{id}}.length; i++){
                tree_{{id}}.treeview('uncheckNode', highlighted_items_{{id}}[i]);
                tree_{{id}}.treeview('unselectNode', highlighted_items_{{id}}[i]);
            }
    }
});


// a function for controlling the behavior of the search box
// provided with the expandable tree:
function initSearch_{{id}}(searchBox){

    var value = searchBox.val();
    tree_{{id}}.treeview('search', [ value, {
        ignoreCase: true,     // case insensitive
        exactMatch: false,    // like or equals
        revealResults: true,  // reveal matching nodes
    }])
    $("#select-highlighted-checkbox-{{id}}").prop('checked', false);
    tree_{{id}}.treeview('uncheckAll');
    var selectedNodes = tree_{{id}}.treeview('getSelected');
    for(item in selectedNodes){
        console.log('unselect: ' + selectedNodes[item]);
        tree_{{id}}.treeview('unselectNode', selectedNodes[item].nodeId);
    }
}

$("#tree-filter-button-{{id}}").click(function(e){
    var target = e.target; //the filter
    var searchBoxId = $(target).attr("filterTarget");
    console.log(searchBoxId);
    var searchBox = $("#" + searchBoxId);
    initSearch_{{id}}(searchBox);
});


}

// load files dynamically:
function loadFiles_{{id}}(){
    $.ajax({
        url:"/resources/tree/?include_uploads=true&regex_filter={{regex_filter}}",
        type:"GET",
        headers:{"X-CSRFToken": csrfToken},
        success:function(response){
            $("#file-choice-tree-{{id}}").treeview({
                    data: response,
                    multiSelect: true,
                    showCheckbox: true,
                    checkedIcon: "far fa-check-square",
                    uncheckedIcon: "far fa-square",
                    expandIcon: "far fa-plus-square",
                    collapseIcon: "far fa-minus-square",
                    showBorder: false,
                    highlightSelected: false,
                    levels: 1,
                    searchResultColor: "#155724",
                    searchResultBackColor:"#d4edda"
                });
                attach_functions_tree_{{id}}();
            if (response.length === 0){
                $("#file-choice-tree-{{id}}").html("<p class=\"alert alert-warning\">No files are available</p>");
            }
        },
        error:function(){
            console.log('error!');
        }
    });
}
loadFiles_{{id}}();

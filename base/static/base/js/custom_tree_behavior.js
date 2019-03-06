/*
******************************************************
START code for expandable tree 
******************************************************
*/

var highlighted_items = {};

function setupMethods(treeID){

    // add a key for this tree.  This way all the highlighted items
    // are tracked in the same object
    highlighted_items[treeID] = [];

    // jQuery object for the tree
    var el = $("#"+treeID);

    // register method to run when the search is done
    el.on('searchComplete', function(event, data) {
        console.log("searchComplete!!!!!!!!!!!: " + JSON.stringify(data));
        highlighted_items[treeID] = [];
        for(var item in data){
            highlighted_items[treeID].push(data[item].nodeId);
        }
        console.log('HLI: ' + JSON.stringify(highlighted_items));
    });

    // This lets us know which items were "unhighlighted" following a new search
    el.on('searchCleared', function(event, data){
        console.log("searchCleared: " + JSON.stringify(data));
        console.log("searchCleared: " + treeID);
        console.log(data.length);
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
        //var currentTree = $("#"+treeID);
        var currentTree = el;
        allParents.forEach(
                function(values){
                        console.log('val: ' + values);
                        currentTree.treeview('collapseNode', values);
                }
        );
    });

    // This allows us to check children by checking the parent node
    el.on('nodeChecked', function(event, node){
        var children = node.nodes;
        var currentTree = $("#"+treeID);
        for(item in children){
            console.log(item);
            var nodeId = children[item].nodeId;
            currentTree.treeview('checkNode', nodeId);
            currentTree.treeview('selectNode', nodeId);
        }
        currentTree.treeview('expandNode', node.nodeId);
        currentTree.treeview('selectNode', node.nodeId);
    });

    // This allows us to uncheck all the children by unclicking the parent
    el.on('nodeUnchecked', function(event, node){
        //get any children and uncheck them as well.  Note only goes down ONE layer.
        var children = node.nodes;
        var currentTree = $("#"+treeID);
        for(item in children){
            console.log(item);
            var nodeId = children[item].nodeId;
            currentTree.treeview('uncheckNode', nodeId);
            currentTree.treeview('unselectNode', nodeId);
        }
        currentTree.treeview('collapseNode', node.nodeId);
        currentTree.treeview('unselectNode', node.nodeId);
    });

    $(".select-highlighted-checkbox[treeTarget='" + treeID +"']").change(function(e) {
        console.log('clicked!');
        console.log('on click, tgreeTarget=' + treeID);
        var currentTree = $('#' + treeID);
        console.log("CT: " +JSON.stringify(currentTree));
        var hl = highlighted_items[treeID];
        if(this.checked){
                console.log('was checked');
                console.log(highlighted_items);
                for(var i=0; i < hl.length; i++){
                    currentTree.treeview('checkNode', hl[i]);
                    currentTree.treeview('selectNode', hl[i]);
                }
                var selectedNodes = currentTree.treeview('getSelected');
                console.log(selectedNodes)
        } else {
                console.log('was unchecked');
                for(var i=0; i < hl.length; i++){
                    currentTree.treeview('uncheckNode', hl[i]);
                    currentTree.treeview('unselectNode', hl[i]);
                }
        }
    });
}

// a function for controlling the behavior of the search box
// provided with the expandable tree:

function initSearch(searchBox){

    var value = searchBox.val();
    var treeTarget = searchBox.attr("treeTarget");
    console.log(value);
    console.log('treeTarget: '+treeTarget);
    var currentTree = $('#' + treeTarget);
    console.log(currentTree);
    currentTree.treeview('search', [ value, {
        ignoreCase: true,     // case insensitive
        exactMatch: false,    // like or equals
        revealResults: true,  // reveal matching nodes
    }])
    $(".select-highlighted-checkbox[treeTarget='"+treeTarget+"']").prop('checked', false);
    currentTree.treeview('uncheckAll');
    var selectedNodes = currentTree.treeview('getSelected');
    for(item in selectedNodes){
        console.log('unselect: ' + selectedNodes[item]);
        currentTree.treeview('unselectNode', selectedNodes[item].nodeId);
    }
}

$(".tree-filter").each(function(){
    var el = $(this);
    el.click(function(e){
        var target = e.target; //the filter
        var searchBoxId = $(target).attr("filterTarget");
        console.log(searchBoxId);
        var searchBox = $("#" + searchBoxId);
        initSearch(searchBox);
    });
});

$(".tree-search").each(function(){
    var el = $(this);
    el.keyup(function(e){
        if(e.keyCode === 13){
            initSearch(el);
        }
    });
});

/*
******************************************************
END code for expandable tree 
******************************************************
*/

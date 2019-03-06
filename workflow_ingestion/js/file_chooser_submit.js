    var tree = $("#file-choice-tree-{{id}}");
    var selected = tree.treeview('getSelected');

    if(selected.length > 0){
        var selectedPks = [];
        for(var i in selected){
            var pk = selected[i].pk;
            selectedPks.push(pk);
        }
        var dataTarget = tree.attr("dataTarget");
        payload[dataTarget] = selectedPks;
    } else {
        console.log('Nothing selected!');
    }

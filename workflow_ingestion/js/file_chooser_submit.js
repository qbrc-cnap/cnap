    var tree_{{id}} = $("#file-choice-tree-{{id}}");
    var selected_{{id}} = tree_{{id}}.treeview('getSelected');
    var dataTarget = tree_{{id}}.attr("dataTarget");

    // need to first get rid of non-leaves:
    var selectedPks_{{id}} = [];
    for(var i in selected_{{id}}){
        var pk = selected_{{id}}[i].pk;
        if(pk !== undefined){
            selectedPks_{{id}}.push(pk);
        }
    }

    if(selectedPks_{{id}}.length > 0){
        {% if choose_multiple %}
          payload[dataTarget] = selectedPks_{{id}};
        {% else %}
          if(selectedPks_{{id}}.length > 1){
            form_problems.push("You have selected more than one file where we accept only a single file.  Please check your inputs.");
            return;
          }
          payload[dataTarget] = selectedPks_{{id}}[0];
        {% endif %}
    } else {
        console.log('Nothing selected!');
        form_problems.push("You have not selected any files.  Please check that you have checked the box.");
        return;
    }

    var tree = $("#file-choice-tree-{{id}}");
    var selected = tree.treeview('getSelected');
    var dataTarget = tree.attr("dataTarget");

    if(selected.length > 0){
        {% if choose_multiple %}
          var selectedPks = [];
          for(var i in selected){
            var pk = selected[i].pk;
            selectedPks.push(pk);
          }
          payload[dataTarget] = selectedPks;
        {% else %}
          if(selected.length > 1){
            form_problems.push("You have selected more than one file where we accept only a single file.  Please check your inputs.");
            return;
          }
          var selectedPk = selected[0].pk; 
          payload[dataTarget] = selectedPk;
        {% endif %}
    } else {
        console.log('Nothing selected!');
        form_problems.push("You have not selected any files.  Please check that you have checked the box.");
        return;
    }

        var el = $("#text-{{id}}");
        var dataTarget = $(el).attr("dataTarget");

        if(!el[0].checkValidity()){
            form_problems.push("There was an empty text field.");
            return;
        }
        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            {% if normalize_input %}
                var pattern1 = /\s+/g;
                val = val.replace(pattern1, '_');
                var pattern2 = /^[\-_a-zA-Z0-9]+$/;
                if (!val.match(pattern2) && val.length > {{min_length}} ){
                    form_problems.push("The value of \""+ val  +"\" was unexpected.  Please enter a value with only letters, numbers, underscores (\"_\"), and dashes (\"-\")");
                    return;
                }
            {% endif %}
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }

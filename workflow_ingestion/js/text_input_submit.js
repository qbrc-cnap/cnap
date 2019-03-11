        var el = $("#text-{{id}}");
        var dataTarget = $(el).attr("dataTarget");

        if(!el[0].checkValidity()){
            form_problems.push("There was an empty text field.");
            return;
        }
        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }

        var el = $("#radio-{{id}}");
        var dataTarget = $(el).attr("dataTarget");

        if (typeof dataTarget !== typeof undefined && dataTarget !== false) {
            // Element has this attribute
            var val = el.val();
            payload[dataTarget] = val;
        } else{
            console.log('Does not have dataTarget attr');
        }

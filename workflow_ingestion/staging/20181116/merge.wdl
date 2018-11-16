task MergeTask {
    Array[File] count_files
    String fname

    command {
        cat ${sep=" " count_files} > ${fname}
    }

    output {
        File mergedCounts = "${fname}"
    }
}

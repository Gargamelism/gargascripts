# gargascripts
place for my scripts

## File Hasher
This is mainly to find duplicates, after running the script find duplicates using query
```SQL
SELECT "path" FROM (
	SELECT md5, 
		"path", 
		ROW_NUMBER() OVER (PARTITION BY md5 ORDER BY LENGTH("path")) AS duplicate_num  
	FROM file_hashes fh
	) fh_w_duplicate_num
	WHERE fh_w_duplicate_num.duplicate_num > 1
	ORDER BY fh_w_duplicate_num.duplicate_num DESC
;
```
Delete duplicates using
```BASH
xargs rm < duplicates.txt
```
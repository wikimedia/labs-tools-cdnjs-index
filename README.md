cdnjs index
===========

Generate an index of all of the libraries mirrored to tools-static via
https://github.com/cdnjs/cdnjs.

Usage
-----
```
$ python generate.py \
  template.html \
  https://tools-static.wmflabs.org/cdnjs/packages.json \
  $HOME/public_html/index.html
```

License
-------
Copyright (C) 2015 Yuvi Panda <yuvipanda@gmail.com>

Licensed under the MIT license. See the [LICENSE](LICENSE) file for more
details.

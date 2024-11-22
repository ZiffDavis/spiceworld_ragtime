# Ragtime
### Generic Utility for Preparing Documents and Configuring a Document Q&A Chatbot

## Overview
This utility was pulled from the generic chatbot code, since we've seen other use cases for interpreting multiple filetypes and extracting information and images from those files.

It still has roots in document Q&A, though, so there are functions for creating embeddings from the extracted text and for intializing prompt data stores in support of a chatbot used to interrogate the documents.

## Usage

```
> python main.py --help

Usage: main.py [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  build-docs
  index-docs
  query
```

### Extracting Text

Use the `build-docs` command to parse a single document or a folder of documents and store the resulting text in a file named `processed_docs.json` in the root project directory.

```
> python main.py build-docs --help

Usage: main.py build-docs [OPTIONS]

Options:
  -i, --include_images
  -f, --force_overwrite
  --config TEXT
  --file TEXT
  --folder TEXT
  --help   Show this message and exit.
```

The salient portions of your config are these:
```    
"content_settings": {
      "document_file":"processed_docs.json", /* For output */
      "text_has_labels":true,
      "label_order": ["Section","Content"],
      "editor_fields": {
          "Section": {
              "ui_name": "Information Category",
              "type": "textfield"
          },
          "Content": {
              "ui_name": "Information",
              "type": "textarea",
              "is_content":true
          }
        }
      }
```

### Creating Vector Store

```
Usage: main.py index-docs [OPTIONS]

Options:
  --config TEXT
  --help         Show this message and exit.
```


### Interrogating the Documents (Chatbot)

```
Usage: main.py query [OPTIONS]

Options:
  --config TEXT
  --help         Show this message and exit.
```


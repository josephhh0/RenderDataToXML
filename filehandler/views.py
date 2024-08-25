import mimetypes
import pandas as pd
import json
import xml.etree.ElementTree as ET
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from xml.dom import minidom
import csv
import io
from .serializers import FileUploadSerializer

class FileUploadView(APIView):
    def post(self, request, *args, **kwargs):
        # Basic example logic for file upload
        return Response({"message": "File uploaded successfully"}, status=status.HTTP_200_OK)

class FileTransformView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = FileUploadSerializer(data=request.data)
        if serializer.is_valid():
            file = request.FILES['file']
            file_type = self.detect_file_type(file)
            
            try:
                if file_type == 'application/json':
                    # Handle JSON
                    file_content = file.read().decode('utf-8')
                    xml_output = self.transform_json_to_xml(file_content)
                
                elif file_type in ['text/csv', 'application/vnd.ms-excel']:
                    # Handle CSV
                    xml_output = self.transform_csv_to_xml(file)
                
                elif file_type == 'application/xml':
                    # Handle XML
                    xml_content = file.read().decode('utf-8')
                    xml_root = ET.fromstring(xml_content)
                    
                    if self.detect_xml_structure(xml_root) == 'attributes':
                        transformed_xml = self.transform_attributes_to_nested(xml_root)
                        xsd_output = self.generate_xsd_from_xml(transformed_xml)
                        xml_output = self.prettify_xml(transformed_xml)
                    else:
                        xml_output = self.prettify_xml(xml_root)
                        xsd_output = self.generate_xsd_from_xml(xml_root)

                    return Response({
                        'xml': xml_output,
                        'xsd': xsd_output
                    }, status=status.HTTP_200_OK)
                
                # Generate XSD for JSON and CSV transformations
                xsd_output = self.generate_xsd_from_xml(ET.fromstring(xml_output))
                
                return Response({
                    'xml': xml_output.replace("\n", "").replace("\r", ""),
                    'xsd': xsd_output.replace("\n", "").replace("\r", "")
                }, status=status.HTTP_200_OK)
            
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def detect_file_type(file):
        mime_type, _ = mimetypes.guess_type(file.name)
        return mime_type if mime_type else 'unknown'

    @staticmethod
    def transform_json_to_xml(file_content):
        data = json.loads(file_content)
        return FileTransformView.json_to_xml(data)

    @staticmethod
    def json_to_xml(json_obj, root_tag="root"):
        element = ET.Element(root_tag)

        def build_tree(d, parent):
            for key, value in d.items():
                sub_element = ET.Element(key)
                parent.append(sub_element)
                if isinstance(value, dict):
                    build_tree(value, sub_element)
                elif isinstance(value, list):
                    for item in value:
                        item_element = ET.Element("item")
                        item_element.text = str(item)
                        sub_element.append(item_element)
                else:
                    sub_element.text = str(value)

        build_tree(json_obj, element)
        return ET.tostring(element, encoding='unicode')

    @staticmethod
    def transform_csv_to_xml(file):
        file_like_object = io.StringIO(file.read().decode('utf-8'))
        delimiter = FileTransformView.detect_delimiter(file_like_object)
        file_like_object.seek(0) 
        
        try:
            df = pd.read_csv(file_like_object, delimiter=delimiter)
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
        
        return FileTransformView.csv_to_xml(df)

    @staticmethod
    def detect_delimiter(file_like_object):
        sample = file_like_object.read(1024)
        sniffer = csv.Sniffer()
        file_like_object.seek(0)  
        delimiter = sniffer.sniff(sample).delimiter
        return delimiter

    @staticmethod
    def csv_to_xml(df):
        root = ET.Element('Root')
        for _, row in df.iterrows():
            item = ET.SubElement(root, 'Item')
            for col in df.columns:
                child = ET.SubElement(item, col.replace(' ', '_'))
                child.text = str(row[col])
        return ET.tostring(root, encoding='unicode')

    @staticmethod
    def process_xml(xml_content):
        root = ET.fromstring(xml_content)
        return FileTransformView.prettify_xml(root)

    @staticmethod
    def prettify_xml(elem):
        rough_string = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="").replace("\n", "").replace("\r", "")

    @staticmethod
    def transform_attributes_to_nested(xml_file):
        def transform_element(element):
            new_element = ET.Element(element.tag)
            for attr_name, attr_value in element.attrib.items():
                child_element = ET.Element(attr_name)
                child_element.text = attr_value
                new_element.append(child_element)
            for child in element:
                new_child = transform_element(child)
                new_element.append(new_child)
            return new_element

        tree = ET.parse(xml_file)
        root = tree.getroot()
        transformed_root = transform_element(root)
        return transformed_root

    @staticmethod
    def detect_xml_structure(root):
        """
        Détecte si le XML est principalement basé sur des attributs ou sur une structure imbriquée.
        """
        def has_attributes(element):
            return bool(element.attrib)

        def has_nested_children(element):
            return any(child for child in element)

        if has_attributes(root):
            return 'attributes'
        elif has_nested_children(root):
            return 'nested'
        return 'unknown'

    @staticmethod
    def process_element(element):
        xsd_element = {
            'attributes': {},
            'children': {}
        }

        for attr_name, attr_value in element.attrib.items():
            xsd_element['attributes'][attr_name] = FileTransformView.type_element(attr_value)

        for child in element:
            child_name = child.tag
            if child_name not in xsd_element['children']:
                xsd_element['children'][child_name] = FileTransformView.process_element(child)
            else:
                for attr_name, attr_type in FileTransformView.process_element(child)['attributes'].items():
                    xsd_element['attributes'][attr_name] = attr_type
                for grandchild_name, grandchild_info in FileTransformView.process_element(child)['children'].items():
                    if grandchild_name not in xsd_element['children'][child_name]['children']:
                        xsd_element['children'][child_name]['children'][grandchild_name] = grandchild_info

        if element.text and not list(element): 
            xsd_element['type'] = FileTransformView.type_element(element.text.strip())

        return xsd_element

    @staticmethod
    def build_xsd(element_name, element_info, level=0):
        xsd = []
        indent = '  ' * level

        xsd.append(f"{indent}<xs:element name=\"{element_name}\"")

        if 'type' in element_info:
            xsd[-1] += f" type=\"{element_info['type']}\"/>"
            return xsd

        xsd[-1] += '>'

        has_children = bool(element_info['children'])
        has_attributes = bool(element_info['attributes'])

        if has_children or has_attributes:
            xsd.append(f"{indent}  <xs:complexType>")

            if has_children:
                xsd.append(f"{indent}    <xs:sequence>")
                for child_name, child_info in element_info['children'].items():
                    xsd.extend(FileTransformView.build_xsd(child_name, child_info, level + 3))
                xsd.append(f"{indent}    </xs:sequence>")

            if has_attributes:
                for attr_name, attr_type in element_info['attributes'].items():
                    xsd.append(f"{indent}    <xs:attribute name=\"{attr_name}\" type=\"{attr_type}\" use=\"required\"/>")

            xsd.append(f"{indent}  </xs:complexType>")

        xsd.append(f"{indent}</xs:element>")
        return xsd

    @staticmethod
    def generate_xsd_from_xml(root):
        xsd_elements = FileTransformView.process_element(root)
        xsd_schema = ['<?xml version="1.0" encoding="UTF-8"?>']
        xsd_schema.append('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">')
        xsd_schema.extend(FileTransformView.build_xsd(root.tag, xsd_elements))
        xsd_schema.append('</xs:schema>')
        return ''.join(xsd_schema).replace("\n", "").replace("\r", "")

    @staticmethod
    def xml_to_xsd(xml_input):
        if isinstance(xml_input, str):
            tree = ET.parse(xml_input)
            root = tree.getroot()
        elif isinstance(xml_input, ET.Element):
            root = xml_input
        else:
            raise TypeError("Expected a file path or an Element object.")
        
        xsd_string = FileTransformView.generate_xsd_from_xml(root)
        return xsd_string

    @staticmethod
    def type_element(value):
        if value.isdigit():
            return 'xs:integer'
        try:
            float(value)
            return 'xs:float'
        except ValueError:
            pass
        
        if value.lower() in ['true', 'false']:
            return 'xs:boolean'
        
        return 'xs:string'
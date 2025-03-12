"""Flow for processing large documents with automatic chunking and token management."""

from typing import List, Dict, Any, Optional, Union, Callable

from app.config import config
from app.flow.base import BaseFlow
from app.llm import LLM
from app.logger import logger
from app.schema import Message
from app.utils.document_chunker import process_document_in_chunks, estimate_tokens


class DocumentProcessorFlow(BaseFlow):
    """
    A flow that handles large documents by automatically chunking them
    and processing each chunk with proper token awareness.
    """
    
    def __init__(self, llm: Optional[LLM] = None):
        """Initialize the document processor flow."""
        super().__init__(name="document_processor", llm=llm or LLM())
        self.document = ""
        self.results = []
        self.current_chunk = 0
        self.total_chunks = 0
        self.max_tokens = config.document_processing.max_chunk_size
        self.chunk_overlap = config.document_processing.chunk_overlap
        
    def preprocess_document(self, document: str) -> List[Dict[str, Any]]:
        """
        Preprocess a document by checking its token count and splitting if necessary.
        
        Args:
            document: The document text to process
            
        Returns:
            Metadata about the document and chunking
        """
        estimated_tokens = estimate_tokens(document)
        logger.info(f"Document size: ~{estimated_tokens} tokens")
        
        # If document exceeds 80% of context window, we need to chunk it
        context_window = config.llm.deepseek.context_window
        safety_threshold = int(context_window * (1 - config.document_processing.token_safety_margin))
        
        needs_chunking = estimated_tokens > safety_threshold
        
        return {
            "document_tokens": estimated_tokens,
            "context_window": context_window,
            "safety_threshold": safety_threshold,
            "needs_chunking": needs_chunking,
            "estimated_chunks": max(1, estimated_tokens // self.max_tokens) if needs_chunking else 1
        }
    
    def process_large_document(
        self, 
        document: str,
        process_function: Callable,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Process a large document with automatic chunking.
        
        Args:
            document: The document text to process
            process_function: Function to process each chunk
            system_prompt: Optional system prompt to prepend to each chunk
            **kwargs: Additional arguments to pass to the process function
            
        Returns:
            Results from processing all chunks
        """
        self.document = document
        metadata = self.preprocess_document(document)
        
        if not metadata["needs_chunking"]:
            # Document fits in one chunk, process directly
            logger.info("Document fits in single chunk, processing directly")
            result = process_function(document, **kwargs)
            self.results = [{
                "chunk_number": 1,
                "total_chunks": 1,
                "result": result
            }]
        else:
            # Document needs chunking
            logger.info(f"Processing document in approximately {metadata['estimated_chunks']} chunks")
            
            # Add system prompt context if provided
            if system_prompt:
                kwargs["system_prompt"] = system_prompt
                
            # Process in chunks
            self.results = process_document_in_chunks(
                document,
                process_function,
                max_tokens=self.max_tokens,
                overlap_tokens=self.chunk_overlap,
                **kwargs
            )
            
        self.total_chunks = len(self.results)
        return self.results
    
    def llm_process_chunk(
        self, 
        chunk: str, 
        chunk_context: Dict[str, Any],
        system_prompt: Optional[str] = None,
        instructions: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """
        Process a document chunk with the LLM, including chunk context metadata.
        
        Args:
            chunk: The text chunk to process
            chunk_context: Metadata about this chunk's position in the document
            system_prompt: Optional system prompt for this processing
            instructions: Instructions for what to do with this chunk
            temperature: LLM temperature setting
            
        Returns:
            LLM's response for this chunk
        """
        # Format chunk context information for the LLM
        chunk_info = (
            f"[This is chunk {chunk_context['chunk_number']} of {chunk_context['total_chunks']}. "
            f"{'This is the first chunk.' if chunk_context['is_first_chunk'] else ''} "
            f"{'This is the last chunk.' if chunk_context['is_last_chunk'] else ''}"
            f"]"
        )
        
        # Prepare messages
        messages = []
        
        # Add chunk context information
        messages.append(Message(role="system", content=chunk_info))
        
        # Add custom system prompt if provided
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
            
        # Add instructions if provided
        if instructions:
            messages.append(Message(role="user", content=instructions))
            
        # Add the document chunk
        messages.append(Message(role="user", content=chunk))
        
        # Process with LLM
        result = self.llm.ask(messages, temperature=temperature)
        return result
        
    def execute(self, user_query: str) -> str:
        """
        Execute the document processor flow based on user query.
        
        Args:
            user_query: The user's query containing the document to process
            
        Returns:
            Processed response or error message
        """
        try:
            # For demonstration, we'll process the user query directly
            # In practice, you would extract the document and specific instructions from the query
            
            # Process the document
            results = self.process_large_document(
                document=user_query,
                process_function=self.llm_process_chunk,
                instructions="Please analyze this document and provide your insights."
            )
            
            # Combine results for return
            if len(results) == 1:
                return results[0]["result"]
            else:
                # Create a summary combining multiple chunk results
                summary = f"I've processed your document in {len(results)} chunks. Here are the key insights:\n\n"
                
                for i, chunk_result in enumerate(results):
                    summary += f"--- Chunk {i+1}/{len(results)} ---\n"
                    summary += chunk_result["result"]
                    summary += "\n\n"
                    
                return summary
                
        except Exception as e:
            logger.error(f"Error in DocumentProcessorFlow: {str(e)}")
            return f"Error processing your document: {str(e)}" 